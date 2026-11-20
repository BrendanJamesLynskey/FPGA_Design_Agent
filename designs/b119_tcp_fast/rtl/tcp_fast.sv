// tcp_fast.sv: TCP fast path for OUCH orders (brief 119, option A of the 110 TCP plan).
//
// Software owns the TCP connection (handshake, ACKs, retransmission, SoupBinTCP login and heartbeats). It hands this block the connection's addressing
// and sequence state through a register bus. For each order (the same inputs as ouch_enter of brief 110) the block emits ONE complete Ethernet frame
// (without the FCS): 14 byte Ethernet header, 20 byte IPv4 header, 20 byte TCP header (no options, flags PSH+ACK), and the 59 byte SoupBinTCP
// Unsequenced Data packet carrying the OUCH 5.0 Enter Order: 113 bytes, fifteen 64-bit words, byte 0 in bits 7:0, the last word carrying one byte.
//
// Timing, in clock edges counted from the edge that samples `go` (edge 0). Word k of the segment is loaded into the output registers at edge k:
//   edge 0       word 0 out (destination MAC), state captured, refusal decided
//   edges 1..5   IPv4 checksum (final at edge 2) and TCP checksum (final at edge 5) formed by adding the dynamic fields to the templates' partial sums
//   edge 5       go to the embedded ouch_enter, which streams the frame's eight words at edges 5..12
//   edge 6       word 6 out: window, TCP checksum, urgent pointer and the first two payload bytes
//   edge 14      word 14 out (last payload byte), end of segment, sequence state advanced (or the segment poisoned)
// Speculative start and abort: the segment may start before the risk verdict. `abort` while the segment is in flight ends it at once with the
// poison bit set on the last word (the MAC makes the frame check sequence wrong, the receiver's MAC drops it) and consumes NOTHING: SND.NXT and the
// IP identification stay as they were. A speculative segment still without a verdict at its last word is poisoned too (fail closed).
// Hand-back: a segment that ends unpoisoned produces one `rec_v` pulse with its sequence number, length, IP identification and payload.
// An independent check: the payload sum seen on ouch_enter's own output words must equal the sum the early checksum used (poison if not).
module tcp_fast (
    input  logic        clk,
    input  logic        rst,
    // order side: the inputs and the busy output of ouch_enter
    input  logic        go,
    input  logic        go_spec,
    input  logic [63:0] f_sym,
    input  logic [31:0] f_px,
    input  logic [31:0] f_qty,
    input  logic [31:0] f_ref,
    input  logic        commit,
    input  logic        abort,
    input  logic [7:0]  cfg_tif, cfg_display, cfg_capacity, cfg_ise, cfg_cross, cfg_custtype,
    input  logic [31:0] cfg_minqty,
    output logic        busy,
    output logic        late,          // an abort arrived with no segment in flight (one clock)
    output logic        refuse_v,      // an order was refused (one clock)
    output logic [2:0]  refuse_code,   // 1 not armed, 2 state not valid or stale, 3 window closed, 4 MSS too small, 5 busy
    // segment out (to the MAC)
    output logic        o_v,
    output logic [63:0] o_d,
    output logic        o_sof,
    output logic        o_eof,
    output logic [7:0]  o_keep,
    output logic        o_poison,      // with the last word: the frame check sequence must be made wrong
    // sent-segment record for software (one clock; rec_pay stays until the next segment's payload is captured)
    output logic        rec_v,
    output logic [31:0] rec_seq,
    output logic [15:0] rec_len,
    output logic [15:0] rec_id,
    output logic [511:0] rec_pay,
    // software register bus
    input  logic        sw_we,
    input  logic [4:0]  sw_waddr,
    input  logic [31:0] sw_wdata,
    input  logic [4:0]  sw_raddr,
    output logic [31:0] sw_rdata       // sw_raddr's register, one clock later
);
    localparam logic [15:0] PAYLEN = 16'd59;

    // ---- connection state, written by software
    logic        arm_req, valid, bld;
    logic [1:0]  bph;
    logic [47:0] dmac, smac;
    logic [31:0] sip, dip;
    logic [15:0] sport, dport, mss;
    logic [7:0]  ttl;
    logic [31:0] snd_nxt, snd_una, snd_wnd, rcv_nxt, stale_limit, age;
    logic [15:0] rcv_wnd, ip_id;
    logic [19:0] ip_raw, tcp_raw;
    logic [15:0] ip_tmpl, tcp_tmpl;        // partial checksums of the static fields (not complemented)

    // ---- the segment in flight
    logic [3:0]  ph;
    logic        spec_c, committed;
    logic [63:0] r_sym;
    logic [31:0] r_px, r_qty, r_ref, seq_c, ack_c;
    logic [15:0] win_c, id_c, ipcsum, csum;
    logic [16:0] ip1;
    logic [20:0] pg0, pg1, pg2, pg3, sump, acc;
    logic [18:0] hdr1;
    logic [22:0] tot;
    logic [16:0] f1;
    logic [63:0] prev;
    logic [511:0] pay;

    // ---- counters
    logic [31:0] c_sent, c_poison, c_ref_arm, c_ref_stale, c_ref_win, c_ref_mss, c_busy, c_late, c_nov, c_wrign, c_sumerr, c_cancel0, c_build, c_abort;

    // ---- the order's frame, for the early payload sum (the same layout as ouch_enter; the streaming check below compares it with the real bytes)
    function automatic logic [7:0] hexa(input logic [3:0] n);
        hexa = (n < 4'd10) ? (8'h30 + {4'd0, n}) : (8'h41 + {4'd0, n} - 8'd10);
    endfunction

    logic [511:0] fr;
    always_comb begin
        fr = '0;
        fr[8*0 +: 8] = 8'h00; fr[8*1 +: 8] = 8'h39; fr[8*2 +: 8] = "U"; fr[8*3 +: 8] = "O";
        fr[8*4 +: 8] = r_ref[31:24]; fr[8*5 +: 8] = r_ref[23:16]; fr[8*6 +: 8] = r_ref[15:8]; fr[8*7 +: 8] = r_ref[7:0];
        fr[8*8 +: 8] = "B";
        fr[8*9 +: 8] = r_qty[31:24]; fr[8*10 +: 8] = r_qty[23:16]; fr[8*11 +: 8] = r_qty[15:8]; fr[8*12 +: 8] = r_qty[7:0];
        for (int i = 0; i < 8; i++) fr[8*(13+i) +: 8] = r_sym[8*(7-i) +: 8];
        fr[8*25 +: 8] = r_px[31:24]; fr[8*26 +: 8] = r_px[23:16]; fr[8*27 +: 8] = r_px[15:8]; fr[8*28 +: 8] = r_px[7:0];
        fr[8*29 +: 8] = cfg_tif; fr[8*30 +: 8] = cfg_display; fr[8*31 +: 8] = cfg_capacity; fr[8*32 +: 8] = cfg_ise; fr[8*33 +: 8] = cfg_cross;
        fr[8*34 +: 8] = "F"; fr[8*35 +: 8] = "D"; fr[8*36 +: 8] = "A"; fr[8*37 +: 8] = "1"; fr[8*38 +: 8] = "1"; fr[8*39 +: 8] = "0";
        for (int i = 0; i < 8; i++) fr[8*(40+i) +: 8] = hexa(r_ref[4*(7-i) +: 4]);
        fr[8*48 +: 8] = 8'h00; fr[8*49 +: 8] = 8'h09;
        fr[8*50 +: 8] = 8'd5; fr[8*51 +: 8] = 8'd3;
        fr[8*52 +: 8] = cfg_minqty[31:24]; fr[8*53 +: 8] = cfg_minqty[23:16]; fr[8*54 +: 8] = cfg_minqty[15:8]; fr[8*55 +: 8] = cfg_minqty[7:0];
        fr[8*56 +: 8] = 8'd2; fr[8*57 +: 8] = 8'd4; fr[8*58 +: 8] = cfg_custtype;
    end

    function automatic logic [20:0] gsum(input logic [511:0] v, input int lo, input int hi);
        logic [20:0] s;
        s = '0;
        for (int j = lo; j < hi; j++) s = s + {5'd0, v[8*(2*j) +: 8], v[8*(2*j+1) +: 8]};
        gsum = s;
    endfunction

    // ---- the 56 header bytes (word 6 holds bytes 48 to 55; bytes 54 and 55 are payload and are filled in at the output)
    logic [447:0] hb;
    always_comb begin
        hb = '0;
        for (int i = 0; i < 6; i++) begin
            hb[8*i +: 8]     = dmac[8*(5-i) +: 8];
            hb[8*(6+i) +: 8] = smac[8*(5-i) +: 8];
        end
        hb[8*12 +: 8] = 8'h08; hb[8*13 +: 8] = 8'h00;
        hb[8*14 +: 8] = 8'h45; hb[8*15 +: 8] = 8'h00;
        hb[8*16 +: 8] = 8'h00; hb[8*17 +: 8] = 8'h63;
        hb[8*18 +: 8] = id_c[15:8]; hb[8*19 +: 8] = id_c[7:0];
        hb[8*20 +: 8] = 8'h40; hb[8*21 +: 8] = 8'h00;
        hb[8*22 +: 8] = ttl; hb[8*23 +: 8] = 8'h06;
        hb[8*24 +: 8] = ipcsum[15:8]; hb[8*25 +: 8] = ipcsum[7:0];
        for (int i = 0; i < 4; i++) begin
            hb[8*(26+i) +: 8] = sip[8*(3-i) +: 8];
            hb[8*(30+i) +: 8] = dip[8*(3-i) +: 8];
            hb[8*(38+i) +: 8] = seq_c[8*(3-i) +: 8];
            hb[8*(42+i) +: 8] = ack_c[8*(3-i) +: 8];
        end
        hb[8*34 +: 8] = sport[15:8]; hb[8*35 +: 8] = sport[7:0];
        hb[8*36 +: 8] = dport[15:8]; hb[8*37 +: 8] = dport[7:0];
        hb[8*46 +: 8] = 8'h50; hb[8*47 +: 8] = 8'h18;
        hb[8*48 +: 8] = win_c[15:8]; hb[8*49 +: 8] = win_c[7:0];
        hb[8*50 +: 8] = csum[15:8]; hb[8*51 +: 8] = csum[7:0];
    end

    // ---- the embedded frame builder of brief 110, started at edge 5 and aborted with the segment
    logic        go_pl, abort_now, e_busy, e_late, e_spec, e_v, e_sof, e_eof, e_abort;
    logic [63:0] e_d;
    logic [7:0]  e_keep;
    assign go_pl     = busy && (ph == 4'd5) && !abort_now;
    assign abort_now = abort && busy;
    ouch_enter u_enter (.clk, .rst, .go(go_pl), .go_spec(1'b0), .f_sym(r_sym), .f_px(r_px), .f_qty(r_qty), .f_ref(r_ref), .commit(1'b0), .abort(abort_now),
        .cfg_tif, .cfg_display, .cfg_capacity, .cfg_ise, .cfg_cross, .cfg_custtype, .cfg_minqty, .busy(e_busy), .late(e_late), .spec_pend(e_spec),
        .o_v(e_v), .o_d(e_d), .o_sof(e_sof), .o_eof(e_eof), .o_keep(e_keep), .o_abort(e_abort));

    // ---- decisions at the go edge
    logic        stale, ok_win, ok_mss, go_take, cancel0;
    logic [31:0] flight;
    assign stale   = (stale_limit != 32'd0) && (age > stale_limit);
    assign flight  = snd_nxt - snd_una;
    assign ok_win  = (snd_wnd >= {16'd0, PAYLEN}) && (flight <= (snd_wnd - {16'd0, PAYLEN}));
    assign ok_mss  = (mss >= PAYLEN);
    assign cancel0 = go && abort;
    assign go_take = go && !abort && !busy && arm_req && valid && !stale && ok_win && ok_mss;

    function automatic logic [15:0] fold16(input logic [19:0] x);
        logic [16:0] a;
        a = {1'b0, x[15:0]} + {13'd0, x[19:16]};
        fold16 = a[15:0] + {15'd0, a[16]};
    endfunction

    logic [20:0] pw0, pw1, pw2, pw3;
    logic [19:0] hsum;
    logic [63:0] w_cur;
    logic        fin_poison, sumerr;
    logic [63:0] nw;          // the word that will be loaded at this edge
    logic        nw_last;
    logic [63:0] wmask;
    always_comb begin
        wmask = '0;
        for (int b = 0; b < 8; b++) wmask[8*b +: 8] = {8{e_keep[b]}};
        w_cur = e_d & wmask;
        sumerr = (acc != sump);
        nw = '0;
        nw_last = (ph == 4'd14);
        case (ph)
            4'd1, 4'd2, 4'd3, 4'd4, 4'd5: nw = hb[64*ph +: 64];
            4'd6:  nw = {e_d[15:0], hb[431:384]};
            4'd14: nw = {56'd0, prev[23:16]};
            default: nw = {e_d[15:0], prev[63:16]};
        endcase
        fin_poison = abort_now || (spec_c && !committed && !commit) || sumerr;
    end

    // ---- the register read mux
    logic [31:0] rd;
    always_comb begin
        rd = '0;
        case (sw_raddr)
            5'd0:  rd = {29'd0, busy, valid, arm_req};
            5'd1:  rd = {16'd0, dmac[47:32]};
            5'd2:  rd = dmac[31:0];
            5'd3:  rd = {16'd0, smac[47:32]};
            5'd4:  rd = smac[31:0];
            5'd5:  rd = sip;
            5'd6:  rd = dip;
            5'd7:  rd = {sport, dport};
            5'd8:  rd = {mss, 8'd0, ttl};
            5'd9:  rd = snd_nxt;
            5'd10: rd = snd_una;
            5'd11: rd = snd_wnd;
            5'd12: rd = rcv_nxt;
            5'd13: rd = {16'd0, rcv_wnd};
            5'd14: rd = {16'd0, ip_id};
            5'd15: rd = stale_limit;
            5'd16: rd = c_sent;
            5'd17: rd = c_poison;
            5'd18: rd = c_ref_arm;
            5'd19: rd = c_ref_stale;
            5'd20: rd = c_ref_win;
            5'd21: rd = c_ref_mss;
            5'd22: rd = c_busy;
            5'd23: rd = c_late;
            5'd24: rd = c_nov;
            5'd25: rd = c_wrign;
            5'd26: rd = c_sumerr;
            5'd27: rd = c_cancel0;
            5'd28: rd = c_build;
            5'd29: rd = c_abort;
            default: rd = '0;
        endcase
    end

    logic wr_lock;
    assign wr_lock = busy || bld;

    always_ff @(posedge clk) begin
        o_v <= 1'b0; o_sof <= 1'b0; o_eof <= 1'b0; o_poison <= 1'b0; rec_v <= 1'b0; late <= 1'b0; refuse_v <= 1'b0;
        sw_rdata <= rd;
        if (rst) begin
            arm_req <= 1'b0; valid <= 1'b0; bld <= 1'b0; bph <= '0; busy <= 1'b0; ph <= '0;
            dmac <= '0; smac <= '0; sip <= '0; dip <= '0; sport <= '0; dport <= '0; mss <= '0; ttl <= '0;
            snd_nxt <= '0; snd_una <= '0; snd_wnd <= '0; rcv_nxt <= '0; rcv_wnd <= '0; ip_id <= '0; stale_limit <= '0; age <= '0;
            ip_raw <= '0; tcp_raw <= '0; ip_tmpl <= '0; tcp_tmpl <= '0;
            spec_c <= 1'b0; committed <= 1'b0;
            r_sym <= '0; r_px <= '0; r_qty <= '0; r_ref <= '0; seq_c <= '0; ack_c <= '0; win_c <= '0; id_c <= '0; ipcsum <= '0; csum <= '0;
            ip1 <= '0; pg0 <= '0; pg1 <= '0; pg2 <= '0; pg3 <= '0; sump <= '0; acc <= '0; hdr1 <= '0; tot <= '0; f1 <= '0; prev <= '0; pay <= '0;
            o_d <= '0; o_keep <= '0; refuse_code <= '0; rec_seq <= '0; rec_len <= '0; rec_id <= '0; rec_pay <= '0;
            c_sent <= '0; c_poison <= '0; c_ref_arm <= '0; c_ref_stale <= '0; c_ref_win <= '0; c_ref_mss <= '0; c_busy <= '0; c_late <= '0;
            c_nov <= '0; c_wrign <= '0; c_sumerr <= '0; c_cancel0 <= '0; c_build <= '0; c_abort <= '0;
        end else begin
            if (age != 32'hFFFFFFFF) age <= age + 32'd1;

            // ---- the template build (two edges after the arm write)
            if (bld) begin
                if (bph == 2'd0) begin
                    ip_raw  <= 20'(16'h4500) + 20'(16'h0063) + 20'(16'h4000) + 20'({ttl, 8'h06}) + 20'(sip[31:16]) + 20'(sip[15:0]) + 20'(dip[31:16]) + 20'(dip[15:0]);
                    tcp_raw <= 20'(sip[31:16]) + 20'(sip[15:0]) + 20'(dip[31:16]) + 20'(dip[15:0]) + 20'(16'h0006) + 20'(16'h004F) + 20'(sport) + 20'(dport) + 20'(16'h5018);
                    bph <= 2'd1;
                end else begin
                    ip_tmpl <= fold16(ip_raw); tcp_tmpl <= fold16(tcp_raw);
                    valid <= 1'b1; bld <= 1'b0; c_build <= c_build + 32'd1;
                end
            end

            // ---- register writes
            if (sw_we) begin
                case (sw_waddr)
                    5'd0: begin
                        if (sw_wdata[0]) begin
                            if (wr_lock) c_wrign <= c_wrign + 32'd1;
                            else begin arm_req <= 1'b1; valid <= 1'b0; bld <= 1'b1; bph <= 2'd0; age <= '0; end
                        end else arm_req <= 1'b0;
                    end
                    5'd1, 5'd2, 5'd3, 5'd4, 5'd5, 5'd6, 5'd7, 5'd8: begin
                        if (wr_lock) c_wrign <= c_wrign + 32'd1;
                        else begin
                            valid <= 1'b0;
                            case (sw_waddr)
                                5'd1: dmac[47:32] <= sw_wdata[15:0];
                                5'd2: dmac[31:0]  <= sw_wdata;
                                5'd3: smac[47:32] <= sw_wdata[15:0];
                                5'd4: smac[31:0]  <= sw_wdata;
                                5'd5: sip         <= sw_wdata;
                                5'd6: dip         <= sw_wdata;
                                5'd7: begin sport <= sw_wdata[31:16]; dport <= sw_wdata[15:0]; end
                                default: begin mss <= sw_wdata[31:16]; ttl <= sw_wdata[7:0]; end
                            endcase
                        end
                    end
                    5'd9:  if (wr_lock) c_wrign <= c_wrign + 32'd1; else snd_nxt <= sw_wdata;
                    5'd10: begin snd_una <= sw_wdata; age <= '0; end
                    5'd11: begin snd_wnd <= sw_wdata; age <= '0; end
                    5'd12: begin rcv_nxt <= sw_wdata; age <= '0; end
                    5'd13: begin rcv_wnd <= sw_wdata[15:0]; age <= '0; end
                    5'd14: if (wr_lock) c_wrign <= c_wrign + 32'd1; else ip_id <= sw_wdata[15:0];
                    5'd15: stale_limit <= sw_wdata;
                    5'd31: begin
                        c_sent <= '0; c_poison <= '0; c_ref_arm <= '0; c_ref_stale <= '0; c_ref_win <= '0; c_ref_mss <= '0; c_busy <= '0; c_late <= '0;
                        c_nov <= '0; c_wrign <= '0; c_sumerr <= '0; c_cancel0 <= '0; c_build <= '0; c_abort <= '0;
                    end
                    default: ;
                endcase
            end

            // ---- the order side
            if (go && !busy && abort) begin
                c_cancel0 <= c_cancel0 + 32'd1;
            end else if (go && busy) begin
                c_busy <= c_busy + 32'd1; refuse_v <= 1'b1; refuse_code <= 3'd5;
            end else if (go && !go_take) begin
                refuse_v <= 1'b1;
                if (!arm_req)                 begin refuse_code <= 3'd1; c_ref_arm   <= c_ref_arm + 32'd1;   end
                else if (!valid || stale)     begin refuse_code <= 3'd2; c_ref_stale <= c_ref_stale + 32'd1; end
                else if (!ok_win)             begin refuse_code <= 3'd3; c_ref_win   <= c_ref_win + 32'd1;   end
                else                          begin refuse_code <= 3'd4; c_ref_mss   <= c_ref_mss + 32'd1;   end
            end else if (abort && !busy) begin
                late <= 1'b1; c_late <= c_late + 32'd1;
            end

            if (go_take) begin
                busy <= 1'b1; ph <= 4'd1; spec_c <= go_spec; committed <= commit;
                r_sym <= f_sym; r_px <= f_px; r_qty <= f_qty; r_ref <= f_ref;
                seq_c <= snd_nxt; ack_c <= rcv_nxt; win_c <= rcv_wnd; id_c <= ip_id; acc <= '0;
                o_v <= 1'b1; o_sof <= 1'b1; o_d <= hb[63:0]; o_keep <= 8'hFF;
            end else if (busy) begin
                if (commit) committed <= 1'b1;
                ph <= ph + 4'd1;
                // checksum pipeline
                if (ph == 4'd1) begin
                    ip1  <= {1'b0, ip_tmpl} + {1'b0, id_c};
                    pg0  <= gsum(fr, 0, 8);  pg1 <= gsum(fr, 8, 16); pg2 <= gsum(fr, 16, 24); pg3 <= gsum(fr, 24, 30);
                    hdr1 <= 19'(tcp_tmpl) + 19'(seq_c[31:16]) + 19'(seq_c[15:0]) + 19'(ack_c[31:16]) + 19'(ack_c[15:0]) + 19'(win_c);
                end
                if (ph == 4'd2) begin
                    ipcsum <= ~(ip1[15:0] + {15'd0, ip1[16]});
                    sump   <= pg0 + pg1 + pg2 + pg3;
                end
                if (ph == 4'd3) tot <= {2'd0, sump} + {4'd0, hdr1};
                if (ph == 4'd4) f1  <= {1'b0, tot[15:0]} + {10'd0, tot[22:16]};
                if (ph == 4'd5) csum <= ~(f1[15:0] + {15'd0, f1[16]});
                // payload capture, the streaming check and the previous word
                prev <= e_d;
                if (ph >= 4'd6 && ph <= 4'd13) begin
                    acc <= acc + {5'd0, w_cur[7:0], w_cur[15:8]} + {5'd0, w_cur[23:16], w_cur[31:24]} + {5'd0, w_cur[39:32], w_cur[47:40]} + {5'd0, w_cur[55:48], w_cur[63:56]};
                    pay[64*(ph - 4'd6) +: 64] <= w_cur;
                end
                // the segment's words
                o_v <= 1'b1; o_d <= nw; o_keep <= nw_last ? 8'h01 : 8'hFF;
                if (abort_now || nw_last) begin
                    o_eof <= 1'b1; busy <= 1'b0; ph <= '0;
                    if (fin_poison) begin
                        o_poison <= 1'b1; c_poison <= c_poison + 32'd1;
                        if (abort_now) c_abort <= c_abort + 32'd1;
                        else if (sumerr) c_sumerr <= c_sumerr + 32'd1;
                        else c_nov <= c_nov + 32'd1;
                    end else begin
                        snd_nxt <= seq_c + {16'd0, PAYLEN}; ip_id <= id_c + 16'd1; c_sent <= c_sent + 32'd1;
                        rec_v <= 1'b1; rec_seq <= seq_c; rec_len <= PAYLEN; rec_id <= id_c; rec_pay <= pay;
                    end
                end
            end
        end
    end

    logic unused;
    assign unused = &{1'b0, e_busy, e_late, e_spec, e_sof, e_eof, e_abort, e_v};
endmodule
