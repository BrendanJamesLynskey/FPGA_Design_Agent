// udp_core: UDP command and telemetry endpoint behind the shell register window.
// Packet bytes arrive through window register IN; at the end flag the packet is
// classified (refusal order of the spec), executed, and the reply is built
// serially (header and payload written in one cycle, then a CRC pass over the
// reply buffer, then the trailer). Telemetry frames are built the same way.
module udp_core (
    input  logic        clk,
    input  logic        rst,          // synchronous, active high
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,    // bits 31:9 unused: the window registers are at most 9 bits wide
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    localparam logic [31:0] ID_WORD = 32'h55445031;
    localparam logic [15:0] PERIOD_RESET_VALUE = 16'd100;
    localparam logic [15:0] MIN_PERIOD = 16'd4;
    localparam logic [31:0] CRC_INIT = 32'hFFFFFFFF;

    localparam logic [1:0] S_IDLE = 2'd0;
    localparam logic [1:0] S_CRC  = 2'd1;
    localparam logic [1:0] S_TRL  = 2'd2;

    // ------------------------------------------------------------ state
    // receive side
    logic [7:0]  rb [0:9];            // packet bytes 0..9
    logic [31:0] tr;                  // last four bytes received (trailer when length fits)
    logic [7:0]  pk_n;                // bytes received, saturating
    logic [31:0] crc_run;             // running CRC over the covered bytes
    logic        dec_q;               // end flag seen, decide next cycle

    // registers and counters
    logic [31:0] scratch [0:2];
    logic [31:0] cmds, refused;
    logic [15:0] c_crc, c_short, c_long, c_rep, c_ooo, c_err;
    logic        has_last;
    logic [15:0] last_seq;

    // time and telemetry
    logic [7:0]  tick_pend;
    logic [31:0] ticks;
    logic [15:0] period, phase;
    logic        tele_on, held;
    logic [15:0] fseq, fcount;

    // reply engine
    logic [7:0]  rbuf [0:31];
    logic [1:0]  rstate;
    logic [4:0]  ridx_ctr;
    logic [4:0]  rbase;
    logic [5:0]  rlen;
    logic [31:0] rcrc;

    // frame engine
    logic [7:0]  fbuf [0:31];
    logic [1:0]  fstate;
    logic [4:0]  fidx_ctr;
    logic [31:0] fcrc;

    // window
    logic [6:0]  ridx, tidx;

    // ------------------------------------------------------------ crc steps
    logic [31:0] crc_rx_next, rcrc_next, fcrc_next;
    crc32_byte u_crc_rx (.crc_in(crc_run), .data(win_wdata[7:0]), .crc_out(crc_rx_next));
    crc32_byte u_crc_rp (.crc_in(rcrc),    .data(rbuf[ridx_ctr]), .crc_out(rcrc_next));
    crc32_byte u_crc_fr (.crc_in(fcrc),    .data(fbuf[fidx_ctr]), .crc_out(fcrc_next));

    // ------------------------------------------------------------ window decode
    logic wr_in, wr_tick, wr_ridx, wr_tidx, wr_take;
    assign wr_in   = win_wr && (win_addr == 7'd0);
    assign wr_tick = win_wr && (win_addr == 7'd1);
    assign wr_ridx = win_wr && (win_addr == 7'd3);
    assign wr_tidx = win_wr && (win_addr == 7'd6);
    assign wr_take = win_wr && (win_addr == 7'd8);

    logic rx_last, rx_include;
    logic [8:0] pk_n9, cover_end;
    assign rx_last    = win_wdata[8];
    assign pk_n9      = {1'b0, pk_n};
    assign cover_end  = 9'd4 + {1'b0, rb[1]};
    assign rx_include = (pk_n < 8'd4) || (pk_n9 < cover_end);

    // ------------------------------------------------------------ decision (cycle after end flag)
    logic [7:0]  typ, plen_len;
    logic [15:0] seq, reg16, seq_d;
    logic [8:0]  full_len;
    logic        long_n, short_n, crc_bad, type_ok, len_bad, seq_rep, seq_ooo;
    logic        reg_oob, reg_ro;
    logic        reply_en, st_ok;
    logic [2:0]  status;
    logic        inc_long, inc_short, inc_crc, inc_rep, inc_ooo, inc_err;
    logic        seq_pass, do_write, do_start, do_stop;
    logic [4:0]  plen;
    logic [31:0] rval;
    logic [135:0] spay;

    assign typ      = rb[0];
    assign plen_len = rb[1];
    assign seq      = {rb[2], rb[3]};
    assign reg16    = {rb[4], rb[5]};
    assign seq_d    = seq - last_seq;
    assign full_len = 9'd8 + {1'b0, plen_len};

    always_comb begin
        long_n  = (pk_n >= 8'd2) && ((plen_len > 8'd8) || (pk_n9 > full_len));
        short_n = (pk_n < 8'd4) || (pk_n9 < full_len);
        crc_bad = (~crc_run) != tr;
        type_ok = (typ >= 8'd1) && (typ <= 8'd5);
        case (typ)
            8'd1, 8'd4: len_bad = (plen_len != 8'd2);
            8'd2:       len_bad = (plen_len != 8'd6);
            default:    len_bad = (plen_len != 8'd0);
        endcase
        seq_rep = has_last && (seq_d == 16'd0);
        seq_ooo = has_last && seq_d[15];
        reg_oob = |reg16[15:3];
        reg_ro  = (reg16[2:0] == 3'd0) || reg16[2];

        reply_en  = 1'b1;
        status    = 3'd0;
        inc_long  = 1'b0;
        inc_short = 1'b0;
        inc_crc   = 1'b0;
        inc_rep   = 1'b0;
        inc_ooo   = 1'b0;
        inc_err   = 1'b0;
        seq_pass  = 1'b0;
        if (long_n) begin
            reply_en = 1'b0; inc_long = 1'b1;
        end else if (short_n) begin
            reply_en = 1'b0; inc_short = 1'b1;
        end else if (crc_bad) begin
            reply_en = 1'b0; inc_crc = 1'b1;
        end else if (!type_ok) begin
            status = 3'd1; inc_err = 1'b1;
        end else if (len_bad) begin
            status = 3'd2; inc_err = 1'b1;
        end else if (seq_rep) begin
            status = 3'd4; inc_rep = 1'b1;
        end else if (seq_ooo) begin
            status = 3'd4; inc_ooo = 1'b1;
        end else begin
            seq_pass = 1'b1;
            if ((typ == 8'd1 || typ == 8'd2) && reg_oob) begin
                status = 3'd3; inc_err = 1'b1;
            end else if (typ == 8'd2 && reg_ro) begin
                status = 3'd5; inc_err = 1'b1;
            end
        end
        st_ok    = reply_en && (status == 3'd0);
        do_write = st_ok && (typ == 8'd2);
        do_start = st_ok && (typ == 8'd4);
        do_stop  = st_ok && (typ == 8'd5);

        plen = 5'd0;
        if (st_ok && typ == 8'd1) plen = 5'd4;
        if (st_ok && typ == 8'd3) plen = 5'd17;

        case (reg16[2:0])
            3'd0:    rval = ID_WORD;
            3'd1:    rval = scratch[0];
            3'd2:    rval = scratch[1];
            3'd3:    rval = scratch[2];
            3'd4:    rval = cmds;
            3'd5:    rval = refused;
            3'd6:    rval = {16'b0, period};
            default: rval = ticks;
        endcase
        spay = {cmds[15:0], c_crc, c_short, c_long, c_rep, c_ooo, c_err, fcount, 7'b0, tele_on};
    end

    // ------------------------------------------------------------ ticks and telemetry due
    logic tick_en, due_new;
    assign tick_en = (tick_pend != 8'd0);
    assign due_new = tick_en && tele_on && ((phase + 16'd1) == period) && !held;

    // ------------------------------------------------------------ receive buffer (datapath, no reset)
    always_ff @(posedge clk) begin
        if (wr_in) begin
            if (pk_n < 8'd10) rb[pk_n[3:0]] <= win_wdata[7:0];
            tr <= {win_wdata[7:0], tr[31:8]};
        end
    end

    // ------------------------------------------------------------ reply buffer (datapath, no reset)
    always_ff @(posedge clk) begin
        if (dec_q && reply_en) begin
            rbuf[0] <= typ | 8'h80;
            rbuf[1] <= {5'b0, status};
            rbuf[2] <= rb[2];
            rbuf[3] <= rb[3];
            rbuf[4] <= {3'b0, plen};
            if (typ == 8'd1) begin
                rbuf[5] <= rval[31:24];
                rbuf[6] <= rval[23:16];
                rbuf[7] <= rval[15:8];
                rbuf[8] <= rval[7:0];
            end
            if (typ == 8'd3) begin
                for (int i = 0; i < 17; i++) rbuf[5 + i] <= spay[8*(16-i) +: 8];
            end
        end
        if (rstate == S_TRL) begin
            rbuf[rbase]         <= ~rcrc[7:0];
            rbuf[rbase + 5'd1]  <= ~rcrc[15:8];
            rbuf[rbase + 5'd2]  <= ~rcrc[23:16];
            rbuf[rbase + 5'd3]  <= ~rcrc[31:24];
        end
    end

    // ------------------------------------------------------------ frame buffer (datapath, no reset)
    logic [31:0] ticks_inc;
    assign ticks_inc = ticks + 32'd1;
    always_ff @(posedge clk) begin
        if (due_new) begin
            fbuf[0]  <= 8'hC0;
            fbuf[1]  <= 8'h00;
            fbuf[2]  <= fseq[15:8];
            fbuf[3]  <= fseq[7:0];
            fbuf[4]  <= 8'd8;
            fbuf[5]  <= ticks_inc[31:24];
            fbuf[6]  <= ticks_inc[23:16];
            fbuf[7]  <= ticks_inc[15:8];
            fbuf[8]  <= ticks_inc[7:0];
            fbuf[9]  <= cmds[15:8];
            fbuf[10] <= cmds[7:0];
            fbuf[11] <= refused[15:8];
            fbuf[12] <= refused[7:0];
        end
        if (fstate == S_TRL) begin
            fbuf[13] <= ~fcrc[7:0];
            fbuf[14] <= ~fcrc[15:8];
            fbuf[15] <= ~fcrc[23:16];
            fbuf[16] <= ~fcrc[31:24];
        end
    end

    // ------------------------------------------------------------ control (synchronous reset)
    always_ff @(posedge clk) begin
        if (rst) begin
            pk_n       <= 8'd0;
            crc_run    <= CRC_INIT;
            dec_q      <= 1'b0;
            scratch[0] <= 32'd0;
            scratch[1] <= 32'd0;
            scratch[2] <= 32'd0;
            cmds       <= 32'd0;
            refused    <= 32'd0;
            c_crc      <= 16'd0;
            c_short    <= 16'd0;
            c_long     <= 16'd0;
            c_rep      <= 16'd0;
            c_ooo      <= 16'd0;
            c_err      <= 16'd0;
            has_last   <= 1'b0;
            last_seq   <= 16'd0;
            tick_pend  <= 8'd0;
            ticks      <= 32'd0;
            period     <= PERIOD_RESET_VALUE;
            phase      <= 16'd0;
            tele_on    <= 1'b0;
            held       <= 1'b0;
            fseq       <= 16'd0;
            fcount     <= 16'd0;
            rstate     <= S_IDLE;
            ridx_ctr   <= 5'd0;
            rbase      <= 5'd0;
            rlen       <= 6'd0;
            rcrc       <= CRC_INIT;
            fstate     <= S_IDLE;
            fidx_ctr   <= 5'd0;
            fcrc       <= CRC_INIT;
            ridx       <= 7'd0;
            tidx       <= 7'd0;
        end else begin
            // window writes
            if (wr_ridx) ridx <= win_wdata[6:0];
            if (wr_tidx) tidx <= win_wdata[6:0];

            // packet bytes
            if (wr_in) begin
                if (pk_n != 8'hFF) pk_n <= pk_n + 8'd1;
                if (rx_include) crc_run <= crc_rx_next;
                if (rx_last) dec_q <= 1'b1;
            end

            // tick generator
            if (wr_tick)      tick_pend <= win_wdata[7:0];
            else if (tick_en) tick_pend <= tick_pend - 8'd1;

            if (tick_en) begin
                ticks <= ticks_inc;
                if (tele_on) begin
                    if ((phase + 16'd1) == period) begin
                        phase <= 16'd0;
                        if (!held) begin
                            held   <= 1'b1;
                            fseq   <= fseq + 16'd1;
                            fcount <= fcount + 16'd1;
                        end
                    end else begin
                        phase <= phase + 16'd1;
                    end
                end
            end

            // frame CRC pass
            case (fstate)
                S_CRC: begin
                    fcrc     <= fcrc_next;
                    fidx_ctr <= fidx_ctr + 5'd1;
                    if (fidx_ctr == 5'd12) fstate <= S_TRL;
                end
                S_TRL:   fstate <= S_IDLE;
                default: fstate <= fstate;
            endcase
            if (due_new) begin
                fstate   <= S_CRC;
                fidx_ctr <= 5'd0;
                fcrc     <= CRC_INIT;
            end

            // reply CRC pass
            case (rstate)
                S_CRC: begin
                    rcrc     <= rcrc_next;
                    ridx_ctr <= ridx_ctr + 5'd1;
                    if ((ridx_ctr + 5'd1) == rbase) rstate <= S_TRL;
                end
                S_TRL: begin
                    rlen   <= {1'b0, rbase} + 6'd4;
                    rstate <= S_IDLE;
                end
                default: rstate <= rstate;
            endcase

            // decision
            if (dec_q) begin
                dec_q   <= 1'b0;
                pk_n    <= 8'd0;
                crc_run <= CRC_INIT;
                rlen    <= 6'd0;
                if (reply_en) begin
                    rstate   <= S_CRC;
                    ridx_ctr <= 5'd0;
                    rcrc     <= CRC_INIT;
                    rbase    <= 5'd5 + plen;
                end else begin
                    rstate   <= S_IDLE;
                end
                if (inc_long)  c_long  <= c_long + 16'd1;
                if (inc_short) c_short <= c_short + 16'd1;
                if (inc_crc)   c_crc   <= c_crc + 16'd1;
                if (inc_rep)   c_rep   <= c_rep + 16'd1;
                if (inc_ooo)   c_ooo   <= c_ooo + 16'd1;
                if (inc_err)   c_err   <= c_err + 16'd1;
                if (!st_ok)    refused <= refused + 32'd1;
                if (st_ok)     cmds    <= cmds + 32'd1;
                if (seq_pass) begin
                    has_last <= 1'b1;
                    last_seq <= seq;
                end
                if (do_write) begin
                    case (reg16[1:0])
                        2'd1:    scratch[0] <= {rb[6], rb[7], rb[8], rb[9]};
                        2'd2:    scratch[1] <= {rb[6], rb[7], rb[8], rb[9]};
                        default: scratch[2] <= {rb[6], rb[7], rb[8], rb[9]};
                    endcase
                end
                if (do_start) begin
                    if (reg16 != 16'd0) period <= (reg16 < MIN_PERIOD) ? MIN_PERIOD : reg16;
                    tele_on <= 1'b1;
                    phase   <= 16'd0;
                end
                if (do_stop) begin
                    tele_on <= 1'b0;
                    held    <= 1'b0;
                end
            end

            if (wr_take) held <= 1'b0;
        end
    end

    // ------------------------------------------------------------ window read (registered)
    logic busy, fbusy;
    logic [5:0] tlen;
    assign busy  = dec_q || (rstate != S_IDLE);
    assign fbusy = (fstate != S_IDLE);
    assign tlen  = (held && !fbusy) ? 6'd17 : 6'd0;

    logic [31:0] rword, tword;
    always_comb begin
        logic [8:0] rj, tj;
        logic [7:0] rbyte [0:3];
        logic [7:0] tbyte [0:3];
        for (int k = 0; k < 4; k++) begin
            rj = {ridx, 2'b00} + 9'(k);
            tj = {tidx, 2'b00} + 9'(k);
            rbyte[k] = (rj < {3'b0, rlen}) ? rbuf[rj[4:0]] : 8'h00;
            tbyte[k] = (tj < {3'b0, tlen}) ? fbuf[tj[4:0]] : 8'h00;
        end
        rword = {rbyte[0], rbyte[1], rbyte[2], rbyte[3]};
        tword = {tbyte[0], tbyte[1], tbyte[2], tbyte[3]};
    end

    always_ff @(posedge clk) begin
        if (win_rd) begin
            case (win_addr)
                7'd2:    win_rdata <= {26'b0, rlen};
                7'd3:    win_rdata <= {25'b0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= {26'b0, tlen};
                7'd6:    win_rdata <= {25'b0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'b0, busy, tele_on};
                default: win_rdata <= 32'd0;
            endcase
        end
    end

    assign led = cmds[15:0];
endmodule
