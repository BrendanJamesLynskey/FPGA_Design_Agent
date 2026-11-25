// udp_core: UDP-style command and telemetry endpoint behind the shell register window.
// Single clock, synchronous active-high reset.
//
// Window offsets: 0 IN, 1 TICK, 2 RLEN, 3 RIDX, 4 RWORD, 5 TLEN, 6 TIDX, 7 TWORD, 8 TAKE, 9 STAT.
// Register numbers in read/write payloads are 16 bits, high byte first (read payload 2 bytes,
// write payload 2 bytes register number then 4 bytes value).
// Combinational byte selectors are written as always_comb / assign on signals (not functions reading
// module signals) so every simulator re-evaluates them when the state they read changes.
module udp_core #(
    parameter int NUM_REGS             = 8,
    parameter int MAX_PAYLOAD          = 8,
    parameter int DEFAULT_PERIOD_TICKS = 100,
    parameter int MIN_PERIOD_TICKS     = 4
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,   // bits 31:9 unused: no window register is wider than 9 bits except none
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    localparam logic [31:0] CRC_RESIDUE = 32'hDEBB20E3;
    localparam logic [31:0] CRC_INIT    = 32'hFFFFFFFF;
    localparam logic [15:0] PERIOD_DEF  = 16'(DEFAULT_PERIOD_TICKS);
    localparam logic [15:0] PERIOD_MIN  = 16'(MIN_PERIOD_TICKS);
    localparam logic [7:0]  MAXP        = 8'(MAX_PAYLOAD);
    localparam logic [7:0]  NREGS       = 8'(NUM_REGS);

    typedef enum logic [2:0] {S_IDLE, S_DECIDE, S_BUILD, S_CRC, S_COMMIT} st_t;
    st_t st;

    // ------------------------------------------------------------ window decode
    logic wr_in, wr_tick, wr_ridx, wr_tidx, wr_take;
    assign wr_in   = win_wr && (win_addr == 7'd0);
    assign wr_tick = win_wr && (win_addr == 7'd1);
    assign wr_ridx = win_wr && (win_addr == 7'd3);
    assign wr_tidx = win_wr && (win_addr == 7'd6);
    assign wr_take = win_wr && (win_addr == 7'd8);

    logic pkt_byte;
    assign pkt_byte = wr_in && (st == S_IDLE);

    // ------------------------------------------------------------ packet receive
    logic [7:0]  pb [0:15];
    logic [4:0]  pcnt;          // bytes received, saturating at 31
    logic [31:0] pcrc, pcrc_nx;

    crc32_byte u_pcrc (.crc_in(pcrc), .data(win_wdata[7:0]), .crc_out(pcrc_nx));

    always_ff @(posedge clk) begin
        if (pkt_byte && !pcnt[4]) pb[pcnt[3:0]] <= win_wdata[7:0];
    end

    // ------------------------------------------------------------ classification
    logic [8:0]  need_n;
    logic        c_long, c_short, c_bad, c_typ_ok, c_len_ok, c_seq_bad, c_reg_bad, c_reg_ro, c_regop;
    logic [7:0]  exp_len;
    logic [15:0] c_seq, c_dseq, last;
    logic        have_last;

    assign need_n   = 9'd8 + {1'b0, pb[1]};
    assign c_long   = (pcnt >= 5'd2) && ((pb[1] > MAXP) || ({4'b0, pcnt} > need_n));
    assign c_short  = (pcnt < 5'd4) || ({4'b0, pcnt} < need_n);
    assign c_bad    = (pcrc != CRC_RESIDUE);
    assign c_typ_ok = (pb[0] >= 8'd1) && (pb[0] <= 8'd5);
    always_comb begin
        case (pb[0])
            8'd1:    exp_len = 8'd2;
            8'd2:    exp_len = 8'd6;
            8'd4:    exp_len = 8'd2;
            default: exp_len = 8'd0;
        endcase
    end
    assign c_len_ok  = (pb[1] == exp_len);
    assign c_seq     = {pb[2], pb[3]};
    assign c_dseq    = c_seq - last;
    assign c_seq_bad = have_last && ((c_dseq == 16'd0) || c_dseq[15]);
    assign c_regop   = (pb[0] == 8'd1) || (pb[0] == 8'd2);
    assign c_reg_bad = (pb[4] != 8'd0) || (pb[5] >= NREGS);
    assign c_reg_ro  = (pb[0] == 8'd2) && ((pb[5] == 8'd0) || (pb[5] >= 8'd4));

    logic       n_drop, n_useseq;
    logic [2:0] n_cnt, n_status;
    logic [4:0] n_plen;
    always_comb begin
        n_drop = 1'b0; n_cnt = 3'd0; n_status = 3'd0; n_useseq = 1'b0; n_plen = 5'd0;
        if (c_long) begin
            n_drop = 1'b1; n_cnt = 3'd2;
        end else if (c_short) begin
            n_drop = 1'b1; n_cnt = 3'd1;
        end else if (c_bad) begin
            n_drop = 1'b1; n_cnt = 3'd0;
        end else if (!c_typ_ok) begin
            n_status = 3'd1; n_cnt = 3'd5;
        end else if (!c_len_ok) begin
            n_status = 3'd2; n_cnt = 3'd5;
        end else if (c_seq_bad) begin
            n_status = 3'd4; n_cnt = (c_dseq == 16'd0) ? 3'd3 : 3'd4;
        end else begin
            n_useseq = 1'b1;
            if (c_regop && c_reg_bad) begin
                n_status = 3'd3; n_cnt = 3'd5;
            end else if (c_reg_ro) begin
                n_status = 3'd5; n_cnt = 3'd5;
            end else if (pb[0] == 8'd1) begin
                n_plen = 5'd4;
            end else if (pb[0] == 8'd3) begin
                n_plen = 5'd17;
            end
        end
    end

    // ------------------------------------------------------------ state
    logic        d_drop, d_useseq;
    logic [2:0]  d_cnt, d_status;
    logic [4:0]  d_plen;
    logic [31:0] rd_val;
    logic [4:0]  k;
    logic [1:0]  kc;
    logic [31:0] rcrc, rcrc_nx;
    logic [4:0]  rlen;
    logic [15:0] cmds, refused;
    logic [15:0] cnt [0:5];     // bad check, too short, too long, repeated, out of order, errors
    logic [31:0] scr1, scr2, scr3;
    logic [6:0]  ridx, tidx;

    // telemetry state (declared here, driven below)
    logic [31:0] uptime;
    logic        tel_on, held;
    logic [15:0] period, fcount;
    logic [7:0]  tick_left;

    function automatic logic [31:0] regval(input logic [2:0] r);
        case (r)
            3'd0:    regval = 32'h55445031;
            3'd1:    regval = scr1;
            3'd2:    regval = scr2;
            3'd3:    regval = scr3;
            3'd4:    regval = {16'h0, cmds};
            3'd5:    regval = {16'h0, refused};
            3'd6:    regval = {16'h0, period};
            default: regval = uptime;
        endcase
    endfunction

    // reply byte k, selected combinationally from the decided packet state
    logic [7:0]  rb_cur;
    logic [4:0]  rp;
    logic [15:0] rcv;
    always_comb begin
        rp = k - 5'd5;
        case (rp[4:1])
            4'd0:    rcv = cmds;
            4'd1:    rcv = cnt[0];
            4'd2:    rcv = cnt[1];
            4'd3:    rcv = cnt[2];
            4'd4:    rcv = cnt[3];
            4'd5:    rcv = cnt[4];
            4'd6:    rcv = cnt[5];
            4'd7:    rcv = fcount;
            default: rcv = 16'h0;
        endcase
        case (k)
            5'd0:    rb_cur = pb[0] | 8'h80;
            5'd1:    rb_cur = {5'b0, d_status};
            5'd2:    rb_cur = pb[2];
            5'd3:    rb_cur = pb[3];
            5'd4:    rb_cur = {3'b0, d_plen};
            default: begin
                if (pb[0] == 8'd1) begin
                    case (rp[1:0])
                        2'd0:    rb_cur = rd_val[31:24];
                        2'd1:    rb_cur = rd_val[23:16];
                        2'd2:    rb_cur = rd_val[15:8];
                        default: rb_cur = rd_val[7:0];
                    endcase
                end else if (rp == 5'd16) begin
                    rb_cur = {7'b0, tel_on};
                end else begin
                    rb_cur = rp[0] ? rcv[7:0] : rcv[15:8];
                end
            end
        endcase
    end

    logic [7:0] crc_b;
    logic [31:0] rcrc_fin;
    assign rcrc_fin = ~rcrc;
    assign crc_b    = rcrc_fin[{kc, 3'b000} +: 8];

    crc32_byte u_rcrc (.crc_in(rcrc), .data(rb_cur), .crc_out(rcrc_nx));

    logic [7:0] rbuf [0:31];
    always_ff @(posedge clk) begin
        if (st == S_BUILD)    rbuf[k] <= rb_cur;
        else if (st == S_CRC) rbuf[k] <= crc_b;
    end

    logic ev_ok, ev_start, ev_stop;
    assign ev_ok    = (st == S_COMMIT) && !d_drop && (d_status == 3'd0);
    assign ev_start = ev_ok && (pb[0] == 8'd4);
    assign ev_stop  = ev_ok && (pb[0] == 8'd5);

    always_ff @(posedge clk) begin
        if (rst) begin
            st <= S_IDLE;
            pcnt <= 5'd0;
            pcrc <= CRC_INIT;
            have_last <= 1'b0;
            last <= 16'h0;
            cmds <= 16'h0;
            refused <= 16'h0;
            for (int i = 0; i < 6; i++) cnt[i] <= 16'h0;
            scr1 <= 32'h0; scr2 <= 32'h0; scr3 <= 32'h0;
            ridx <= 7'h0; tidx <= 7'h0;
            rlen <= 5'd0;
        end else begin
            if (wr_ridx) ridx <= win_wdata[6:0];
            if (wr_tidx) tidx <= win_wdata[6:0];
            case (st)
                S_IDLE: begin
                    if (pkt_byte) begin
                        pcrc <= pcrc_nx;
                        if (pcnt != 5'd31) pcnt <= pcnt + 5'd1;
                        if (win_wdata[8]) st <= S_DECIDE;
                    end
                end
                S_DECIDE: begin
                    d_drop   <= n_drop;
                    d_useseq <= n_useseq;
                    d_cnt    <= n_cnt;
                    d_status <= n_status;
                    d_plen   <= n_plen;
                    rd_val   <= regval(pb[5][2:0]);
                    pcnt <= 5'd0;
                    pcrc <= CRC_INIT;
                    rlen <= 5'd0;
                    k    <= 5'd0;
                    kc   <= 2'd0;
                    rcrc <= CRC_INIT;
                    st   <= n_drop ? S_COMMIT : S_BUILD;
                end
                S_BUILD: begin
                    rcrc <= rcrc_nx;
                    k    <= k + 5'd1;
                    if (k == 5'd4 + d_plen) st <= S_CRC;
                end
                S_CRC: begin
                    k  <= k + 5'd1;
                    kc <= kc + 2'd1;
                    if (kc == 2'd3) st <= S_COMMIT;
                end
                S_COMMIT: begin
                    rlen <= d_drop ? 5'd0 : (5'd9 + d_plen);
                    if (d_drop || (d_status != 3'd0)) begin
                        refused <= refused + 16'd1;
                        cnt[d_cnt] <= cnt[d_cnt] + 16'd1;
                    end
                    if (d_useseq) begin
                        last <= c_seq;
                        have_last <= 1'b1;
                    end
                    if (ev_ok) begin
                        cmds <= cmds + 16'd1;
                        if (pb[0] == 8'd2) begin
                            case (pb[5][1:0])
                                2'd1:    scr1 <= {pb[6], pb[7], pb[8], pb[9]};
                                2'd2:    scr2 <= {pb[6], pb[7], pb[8], pb[9]};
                                2'd3:    scr3 <= {pb[6], pb[7], pb[8], pb[9]};
                                default: ;
                            endcase
                        end
                    end
                    st <= S_IDLE;
                end
                default: st <= S_IDLE;
            endcase
        end
    end

    assign led = cmds;

    // ------------------------------------------------------------ ticks and telemetry
    logic        tick, due, fbuilding;
    logic [15:0] tcount, fseq, f_seq, f_cmd, f_ref;
    logic [31:0] f_up, fcrc, fcrc_nx;
    logic [3:0]  fi;
    logic [15:0] per_in;

    assign tick   = (tick_left != 8'd0);
    assign due    = tick && tel_on && (({1'b0, tcount} + 17'd1) >= {1'b0, period});
    assign per_in = {pb[4], pb[5]};

    // telemetry frame bytes (17), crc bytes are the inverted running crc
    logic [7:0] fbv [0:16];
    assign fbv[0]  = 8'hC0;
    assign fbv[1]  = 8'h00;
    assign fbv[2]  = f_seq[15:8];
    assign fbv[3]  = f_seq[7:0];
    assign fbv[4]  = 8'd8;
    assign fbv[5]  = f_up[31:24];
    assign fbv[6]  = f_up[23:16];
    assign fbv[7]  = f_up[15:8];
    assign fbv[8]  = f_up[7:0];
    assign fbv[9]  = f_cmd[15:8];
    assign fbv[10] = f_cmd[7:0];
    assign fbv[11] = f_ref[15:8];
    assign fbv[12] = f_ref[7:0];
    assign fbv[13] = ~fcrc[7:0];
    assign fbv[14] = ~fcrc[15:8];
    assign fbv[15] = ~fcrc[23:16];
    assign fbv[16] = ~fcrc[31:24];

    crc32_byte u_fcrc (.crc_in(fcrc), .data(fbv[{1'b0, fi}]), .crc_out(fcrc_nx));

    always_ff @(posedge clk) begin
        if (rst) begin
            tick_left <= 8'd0;
            uptime    <= 32'h0;
            tel_on    <= 1'b0;
            tcount    <= 16'h0;
            period    <= PERIOD_DEF;
            held      <= 1'b0;
            fseq      <= 16'h0;
            fcount    <= 16'h0;
            fbuilding <= 1'b0;
            fi        <= 4'd0;
        end else begin
            if (wr_tick)   tick_left <= win_wdata[7:0];
            else if (tick) tick_left <= tick_left - 8'd1;
            if (tick) uptime <= uptime + 32'd1;
            if (tick && tel_on) tcount <= due ? 16'h0 : tcount + 16'd1;
            if (fbuilding) begin
                fi <= fi + 4'd1;
                if (fi == 4'd12) fbuilding <= 1'b0;
            end
            if (due && !held) begin
                held      <= 1'b1;
                fseq      <= fseq + 16'd1;
                fcount    <= fcount + 16'd1;
                fi        <= 4'd0;
                fbuilding <= 1'b1;
            end
            if (ev_start) begin
                if (per_in != 16'h0) period <= (per_in < PERIOD_MIN) ? PERIOD_MIN : per_in;
                tel_on <= 1'b1;
                tcount <= 16'h0;
            end
            if (ev_stop) tel_on <= 1'b0;
            if (ev_stop || wr_take) begin
                held      <= 1'b0;
                fbuilding <= 1'b0;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (due && !held) begin
            f_seq <= fseq;
            f_up  <= uptime + 32'd1;
            f_cmd <= cmds;
            f_ref <= refused;
            fcrc  <= CRC_INIT;
        end else if (fbuilding) begin
            fcrc  <= fcrc_nx;
        end
    end

    // ------------------------------------------------------------ readback
    // byte views gated by length / held, indexed by constant positions
    logic [7:0] rview [0:31];
    logic [7:0] tview [0:19];
    genvar gi;
    generate
        for (gi = 0; gi < 32; gi++) begin : g_rv
            assign rview[gi] = (6'(gi) < {1'b0, rlen}) ? rbuf[gi] : 8'h00;
        end
        for (gi = 0; gi < 20; gi++) begin : g_tv
            if (gi < 17) begin : g_in
                assign tview[gi] = held ? fbv[gi] : 8'h00;
            end else begin : g_out
                assign tview[gi] = 8'h00;
            end
        end
    endgenerate

    logic [4:0]  rj, tj;
    logic [31:0] rword, tword;
    assign rj = {ridx[2:0], 2'b00};
    assign tj = {tidx[2:0], 2'b00};
    assign rword = (ridx < 7'd7) ? {rview[rj], rview[rj + 5'd1], rview[rj + 5'd2], rview[rj + 5'd3]} : 32'h0;
    assign tword = (tidx < 7'd5) ? {tview[tj], tview[tj + 5'd1], tview[tj + 5'd2], tview[tj + 5'd3]} : 32'h0;

    logic busy;
    assign busy = (st != S_IDLE);

    always_ff @(posedge clk) begin
        if (win_rd) begin
            case (win_addr)
                7'd2:    win_rdata <= {27'h0, rlen};
                7'd3:    win_rdata <= {25'h0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= held ? 32'd17 : 32'd0;
                7'd6:    win_rdata <= {25'h0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'h0, busy, tel_on};
                default: win_rdata <= 32'h0;
            endcase
        end
    end
endmodule
