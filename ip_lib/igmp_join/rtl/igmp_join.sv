// igmp_join.sv: IGMPv2 host membership for a few configured multicast groups (RFC 2236) (ip_lib, brief 63D).
// Byte-wide AXI-Stream in (received Ethernet frames, FCS removed) and out (frames to send). IGMPv3 (RFC 3376) is not
// implemented: a version 3 query is answered as a version 2 query, as RFC 3376 section 7.2.1 lets a version 2 host do.
//
// Groups: group i is groups[32*i +: 32], a member while group_en[i] is high.
//   - Joining (group_en rises): an unsolicited Membership Report now, repeated once after a random 1..UNSOL_TICKS
//     ticks (RFC 2236 section 3, the Unsolicited Report Interval).
//   - A General Query (group 0) starts a timer for every member group, a Group-Specific Query for that group only: a
//     random delay of 1..Max Response Time ticks (a query's Max Response Time of 0 is a version 1 query: 100 ticks).
//     A running timer is restarted only when the query asks for less than it has left.
//   - When the timer expires the host sends a Membership Report for the group. A report for the group from another
//     host while the timer runs cancels it (suppression).
//   - Leaving (group_en falls): a Leave Group message to 224.0.0.2, when this host sent the last report for the group.
// A tick is TICK_CLKS clocks; RFC 2236 counts in tenths of a second (12_500_000 clocks at 125 MHz).
// Frames sent: Ethernet to 01-00-5E plus the low 23 bits of the IP destination; IPv4 with TTL 1, protocol 2 and the
// Router Alert option (RFC 2113; IHL 6); IGMP type 0x16 (report, to the group) or 0x17 (leave, to 224.0.0.2), with
// both checksums. 46 bytes; the MAC pads them.
// Queries are taken from frames with EtherType 0x0800, a right IP header checksum, protocol 2 and a right IGMP
// checksum over the whole IGMP message (8 bytes for version 2, 12 or more for version 3).

module igmp_join #(
    parameter int N_GROUPS    = 4,              // 1..8
    parameter int TICK_CLKS   = 12_500_000,     // clocks per tick (a tenth of a second), 1..16777215
    parameter int UNSOL_TICKS = 100             // the repeat of a join's report: up to this many ticks, 1..255
) (
    input  logic                   clk,
    input  logic                   rst,
    input  logic [47:0]            own_mac,
    input  logic [31:0]            own_ip,
    input  logic [N_GROUPS*32-1:0] groups,
    input  logic [N_GROUPS-1:0]    group_en,
    input  logic [7:0]             s_axis_tdata,
    input  logic                   s_axis_tvalid,
    output logic                   s_axis_tready,
    input  logic                   s_axis_tlast,
    input  logic                   s_axis_tuser,
    output logic [7:0]             m_axis_tdata,
    output logic                   m_axis_tvalid,
    input  logic                   m_axis_tready,
    output logic                   m_axis_tlast,
    output logic                   ev_query,        // a valid query was received
    output logic                   ev_report,       // a report's last byte left
    output logic                   ev_leave,        // a leave's last byte left
    output logic                   ev_suppressed    // another host's report cancelled one of our timers
);
    localparam int N = N_GROUPS;
    initial begin
        if (N_GROUPS < 1 || N_GROUPS > 8) $error("igmp_join: N_GROUPS must be in 1..8 (got %0d)", N_GROUPS);
        if (TICK_CLKS < 1 || TICK_CLKS > 16777215) $error("igmp_join: TICK_CLKS must be in 1..16777215 (got %0d)", TICK_CLKS);
        if (UNSOL_TICKS < 1 || UNSOL_TICKS > 255) $error("igmp_join: UNSOL_TICKS must be in 1..255 (got %0d)", UNSOL_TICKS);
    end
    assign s_axis_tready = 1'b1;
    function automatic logic [15:0] fold(input logic [31:0] s);
        logic [16:0] t;
        t = {1'b0, s[31:16]} + {1'b0, s[15:0]};
        return t[15:0] + {15'd0, t[16]};
    endfunction

    // ---------------------------------------------------------------- ticks and a random source
    logic [23:0] tc;
    logic        tick;
    logic [15:0] lfsr;
    always_ff @(posedge clk) begin
        if (rst) begin tc <= '0; tick <= 1'b0; lfsr <= 16'hACE1; end
        else begin
            lfsr <= {lfsr[14:0], lfsr[15] ^ lfsr[13] ^ lfsr[12] ^ lfsr[10]};
            tick <= (tc == 24'(TICK_CLKS - 1));
            tc   <= (tc == 24'(TICK_CLKS - 1)) ? '0 : tc + 24'd1;
        end
    end
    function automatic logic [7:0] rnd(input logic [7:0] r, input logic [7:0] span);   // 1..span
        logic [15:0] p;
        p = {8'd0, r} * {8'd0, span};
        return p[15:8] + 8'd1;
    endfunction

    // ---------------------------------------------------------------- receive: queries and other hosts' reports
    logic [15:0] k;
    logic [15:0] et, tl;
    logic [7:0]  vi, proto, typ, mrt;
    logic [31:0] grp;
    logic [31:0] ip_acc, ig_acc;
    logic        fin, f_bad;
    logic [15:0] f_len;
    logic [15:0] g0;                    // the IGMP message's index: 14 + 4 x IHL
    logic [16:0] g_end;
    assign g0    = 16'd14 + {10'd0, vi[3:0], 2'b00};
    assign g_end = {1'b0, tl} + 17'd14;
    logic [15:0] wv;
    assign wv = k[0] ? {8'd0, s_axis_tdata} : {s_axis_tdata, 8'd0};
    always_ff @(posedge clk) begin
        fin <= 1'b0;
        if (rst) begin
            k <= '0; et <= '0; tl <= '0; vi <= '0; proto <= '0; typ <= '0; mrt <= '0; grp <= '0; ip_acc <= '0;
            ig_acc <= '0; f_bad <= 1'b0; f_len <= '0;
        end else if (s_axis_tvalid) begin
            if (k == 16'd0) begin ip_acc <= '0; ig_acc <= '0; end
            case (k)
                16'd12, 16'd13: et <= {et[7:0], s_axis_tdata};
                16'd14:         vi <= s_axis_tdata;
                16'd16, 16'd17: tl <= {tl[7:0], s_axis_tdata};
                16'd23:         proto <= s_axis_tdata;
                default: ;
            endcase
            if (k >= 16'd34) begin
                if (k == g0)       typ <= s_axis_tdata;
                if (k == g0 + 1)   mrt <= s_axis_tdata;
                if (k >= g0 + 16'd4 && k <= g0 + 16'd7) grp <= {grp[23:0], s_axis_tdata};
            end
            if (k == 16'd14 || (k > 16'd14 && k < g0)) ip_acc <= ip_acc + 32'(wv);
            if (k >= 16'd34 && k >= g0 && {1'b0, k} < g_end) ig_acc <= ig_acc + 32'(wv);
            if (s_axis_tlast) begin fin <= 1'b1; f_bad <= s_axis_tuser; f_len <= k + 16'd1; k <= '0; end
            else if (k != 16'hFFFF) k <= k + 16'd1;
        end
    end
    logic igmp_ok, is_query, is_report;
    assign igmp_ok   = fin && !f_bad && et == 16'h0800 && vi[7:4] == 4'd4 && vi[3:0] >= 4'd5 && proto == 8'd2 &&
                       fold(ip_acc) == 16'hFFFF && fold(ig_acc) == 16'hFFFF && {1'b0, f_len} >= g_end &&
                       tl >= {10'd0, vi[3:0], 2'b00} + 16'd8;
    assign is_query  = igmp_ok && typ == 8'h11;
    assign is_report = igmp_ok && (typ == 8'h16 || typ == 8'h12);
    logic [7:0] q_mrt;
    assign q_mrt = (mrt == 8'd0) ? 8'd100 : mrt;

    // ---------------------------------------------------------------- per-group state
    logic [N-1:0] en_q, run, rep_p, lv_p, last_rep;
    logic [7:0]   tmr [N];
    logic [N-1:0] sent_rep, sent_lv;    // one clock: the frame for group i finished
    always_ff @(posedge clk) begin
        ev_query <= 1'b0; ev_suppressed <= 1'b0;
        if (rst) begin
            en_q <= '0; run <= '0; rep_p <= '0; lv_p <= '0; last_rep <= '0;
            for (int i = 0; i < N; i++) tmr[i] <= '0;
        end else begin
            en_q <= group_en;
            if (is_query) ev_query <= 1'b1;
            for (int i = 0; i < N; i++) begin
                if (sent_rep[i]) begin rep_p[i] <= 1'b0; last_rep[i] <= 1'b1; end
                if (sent_lv[i]) lv_p[i] <= 1'b0;
                if (group_en[i] && !en_q[i]) begin                    // join: report now, again after a while
                    rep_p[i] <= 1'b1; run[i] <= 1'b1; tmr[i] <= rnd(lfsr[7:0] ^ 8'(i * 37), 8'(UNSOL_TICKS));
                    lv_p[i] <= 1'b0;
                end else if (!group_en[i] && en_q[i]) begin           // leave
                    run[i] <= 1'b0; rep_p[i] <= 1'b0;
                    if (last_rep[i]) lv_p[i] <= 1'b1;
                    last_rep[i] <= 1'b0;
                end else if (group_en[i]) begin
                    if (is_query && (grp == 32'd0 || grp == groups[32*i +: 32])) begin
                        if (!run[i] || tmr[i] > q_mrt) begin
                            run[i] <= 1'b1; tmr[i] <= rnd(lfsr[7:0] ^ 8'(i * 37), q_mrt);
                        end
                    end else if (is_report && grp == groups[32*i +: 32] && run[i]) begin
                        run[i] <= 1'b0; last_rep[i] <= 1'b0; ev_suppressed <= 1'b1;
                    end else if (run[i] && tick) begin
                        if (tmr[i] <= 8'd1) begin run[i] <= 1'b0; rep_p[i] <= 1'b1; end
                        else tmr[i] <= tmr[i] - 8'd1;
                    end
                end
            end
        end
    end

    // ---------------------------------------------------------------- transmit
    logic          sending, cur_lv;
    logic [2:0]    cur_i;
    logic [31:0]   cur_dst, cur_grp;
    logic [5:0]    j;
    logic [15:0]   ident, ipcs, igcs;
    logic          pick;
    logic [2:0]    pick_i;
    logic          pick_lv;
    always_comb begin
        pick = 1'b0; pick_i = '0; pick_lv = 1'b0;
        for (int i = N - 1; i >= 0; i--) begin
            if (lv_p[i])       begin pick = 1'b1; pick_i = 3'(i); pick_lv = 1'b1; end
            else if (rep_p[i]) begin pick = 1'b1; pick_i = 3'(i); pick_lv = 1'b0; end
        end
    end
    // checksums of the frame about to start
    logic [31:0] n_dst, n_grp;
    assign n_grp = groups[32*pick_i +: 32];
    assign n_dst = pick_lv ? 32'hE000_0002 : n_grp;
    logic [31:0] ip_s, ig_s;
    assign ip_s = 32'h4600 + 32'd32 + {16'd0, ident} + 32'h0102 + {16'd0, own_ip[31:16]} + {16'd0, own_ip[15:0]} +
                  {16'd0, n_dst[31:16]} + {16'd0, n_dst[15:0]} + 32'h9404;
    assign ig_s = {16'd0, pick_lv ? 8'h17 : 8'h16, 8'h00} + {16'd0, n_grp[31:16]} + {16'd0, n_grp[15:0]};
    function automatic logic [7:0] fb(input logic [5:0] i, input logic [31:0] d, input logic [31:0] g, input logic lv,
                                      input logic [47:0] sm, input logic [31:0] si, input logic [15:0] id,
                                      input logic [15:0] ic, input logic [15:0] gc);
        case (i)
            6'd0:  fb = 8'h01;      6'd1:  fb = 8'h00;      6'd2:  fb = 8'h5E;
            6'd3:  fb = {1'b0, d[22:16]};                   6'd4:  fb = d[15:8];    6'd5:  fb = d[7:0];
            6'd6:  fb = sm[47:40];  6'd7:  fb = sm[39:32];  6'd8:  fb = sm[31:24];
            6'd9:  fb = sm[23:16];  6'd10: fb = sm[15:8];   6'd11: fb = sm[7:0];
            6'd12: fb = 8'h08;      6'd13: fb = 8'h00;      6'd14: fb = 8'h46;      6'd15: fb = 8'h00;
            6'd16: fb = 8'h00;      6'd17: fb = 8'd32;      6'd18: fb = id[15:8];   6'd19: fb = id[7:0];
            6'd20: fb = 8'h00;      6'd21: fb = 8'h00;      6'd22: fb = 8'd1;       6'd23: fb = 8'd2;
            6'd24: fb = ic[15:8];   6'd25: fb = ic[7:0];
            6'd26: fb = si[31:24];  6'd27: fb = si[23:16];  6'd28: fb = si[15:8];   6'd29: fb = si[7:0];
            6'd30: fb = d[31:24];   6'd31: fb = d[23:16];   6'd32: fb = d[15:8];    6'd33: fb = d[7:0];
            6'd34: fb = 8'h94;      6'd35: fb = 8'h04;      6'd36: fb = 8'h00;      6'd37: fb = 8'h00;
            6'd38: fb = lv ? 8'h17 : 8'h16;                 6'd39: fb = 8'h00;
            6'd40: fb = gc[15:8];   6'd41: fb = gc[7:0];
            6'd42: fb = g[31:24];   6'd43: fb = g[23:16];   6'd44: fb = g[15:8];    default: fb = g[7:0];
        endcase
    endfunction
    always_ff @(posedge clk) begin
        ev_report <= 1'b0; ev_leave <= 1'b0; sent_rep <= '0; sent_lv <= '0;
        if (rst) begin
            sending <= 1'b0; cur_lv <= 1'b0; cur_i <= '0; cur_dst <= '0; cur_grp <= '0; j <= '0; ident <= '0;
            ipcs <= '0; igcs <= '0; m_axis_tvalid <= 1'b0; m_axis_tdata <= '0; m_axis_tlast <= 1'b0;
        end else if (!sending) begin
            if (pick && !(|sent_rep) && !(|sent_lv)) begin
                sending <= 1'b1; cur_lv <= pick_lv; cur_i <= pick_i; cur_dst <= n_dst; cur_grp <= n_grp; j <= 6'd1;
                ipcs <= ~fold(ip_s); igcs <= ~fold(ig_s);
                m_axis_tvalid <= 1'b1; m_axis_tdata <= 8'h01; m_axis_tlast <= 1'b0;
            end
        end else if (m_axis_tvalid && m_axis_tready) begin
            if (m_axis_tlast) begin
                m_axis_tvalid <= 1'b0; sending <= 1'b0; ident <= ident + 16'd1;
                if (cur_lv) begin ev_leave <= 1'b1; sent_lv <= N'(1) << cur_i; end
                else begin ev_report <= 1'b1; sent_rep <= N'(1) << cur_i; end
            end else begin
                m_axis_tdata <= fb(j, cur_dst, cur_grp, cur_lv, own_mac, own_ip, ident, ipcs, igcs);
                m_axis_tlast <= (j == 6'd45);
                j <= j + 6'd1;
            end
        end
    end
endmodule
