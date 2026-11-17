// udp_endpoint: packet capture, check, execute, reply build, telemetry.
// Single clock, synchronous active-high reset. Window registers per spec.yaml.
module udp_endpoint #(
    parameter logic [31:0] ID_WORD        = 32'h55445031,
    parameter int          DEFAULT_PERIOD = 100,
    parameter int          MIN_PERIOD     = 4,
    parameter int          RNB            = 2     // payload bytes of a read (write needs RNB+4)
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    localparam logic [31:0] CRC_INIT    = 32'hFFFFFFFF;
    localparam logic [31:0] CRC_RESIDUE = 32'hDEBB20E3;   // register after message + its CRC
    localparam logic [1:0]  B_IDLE = 2'd0, B_CRC = 2'd1, B_TRL = 2'd2;
    localparam logic [7:0]  NEED_RD = 8'(RNB);
    localparam logic [7:0]  NEED_WR = 8'(RNB + 4);

    // ---------------------------------------------------------------- window decode
    wire wr_in   = win_wr && (win_addr == 7'd0);
    wire wr_tick = win_wr && (win_addr == 7'd1);
    wire wr_ridx = win_wr && (win_addr == 7'd3);
    wire wr_tidx = win_wr && (win_addr == 7'd6);
    wire wr_take = win_wr && (win_addr == 7'd8);

    // ---------------------------------------------------------------- state
    logic [31:0] rx_crc;
    logic [5:0]  rx_n;
    logic [7:0]  rxb [0:9];
    logic        ev_pend;

    logic [31:0] cmds, refused, uptime;
    logic [15:0] c_crc, c_short, c_long, c_rep, c_ooo, c_tle;
    logic [31:0] scr1, scr2, scr3;
    logic [15:0] last_seq;
    logic        seq_valid;

    logic [15:0] period, tcount;
    logic        tel_on, held;
    logic [15:0] fseq, fcount;
    logic [15:0] pending;
    logic [6:0]  ridx, tidx;

    logic [7:0]  rb [0:31];
    logic [5:0]  rep_len;
    logic [1:0]  b_state;
    logic [4:0]  bidx, blen;
    logic [31:0] bcrc;

    logic [7:0]  fb [0:31];
    logic [1:0]  f_state;     // 0 idle, 1 crc, 2 trailer
    logic [4:0]  fidx;
    logic [31:0] fcrc;

    // ---------------------------------------------------------------- crc engines
    logic [31:0] rx_crc_nx, b_crc_nx, f_crc_nx;
    crc32_byte u_crc_rx (.crc_i(rx_crc), .d(win_wdata[7:0]), .crc_o(rx_crc_nx));
    crc32_byte u_crc_b  (.crc_i(bcrc),   .d(rb[bidx]),       .crc_o(b_crc_nx));
    crc32_byte u_crc_f  (.crc_i(fcrc),   .d(fb[fidx]),       .crc_o(f_crc_nx));

    // ---------------------------------------------------------------- evaluation (combinational)
    wire [7:0]  ty  = rxb[0];
    wire [7:0]  ln  = rxb[1];
    wire [15:0] sq  = {rxb[2], rxb[3]};
    wire [15:0] rg  = {8'h00, rxb[4]};      // register number: first payload byte
    wire [9:0]  full_len = 10'd8 + {2'b0, ln};
    wire [9:0]  n10      = {4'b0, rx_n};
    wire        e_long   = (ln > 8'd8) || (n10 > full_len);
    wire        e_short2 = (n10 < full_len);
    wire        e_crc    = (rx_crc != CRC_RESIDUE);
    wire        known    = (ty >= 8'd1) && (ty <= 8'd5);
    logic [7:0] need;
    always_comb begin
        case (ty)
            8'd1:    need = NEED_RD;
            8'd2:    need = NEED_WR;
            8'd4:    need = 8'd2;
            default: need = 8'd0;
        endcase
    end
    wire        e_len    = (ln != need);
    wire [15:0] dseq     = sq - last_seq;
    wire        d_zero   = (dseq == 16'd0);
    wire        e_seqbad = seq_valid && (d_zero || dseq[15]);
    wire        is_rw    = (ty == 8'd1) || (ty == 8'd2);
    wire        e_regbad = is_rw && (rg[15:3] != 13'd0);
    wire        e_ro     = (ty == 8'd2) && ((rg[2:0] == 3'd0) || rg[2]);

    logic inc_short, inc_long, inc_crc, inc_rep, inc_ooo, inc_tle;
    logic ev_reply, ev_seq_take, ev_exec;
    logic [2:0] ev_status;
    always_comb begin
        inc_short = 1'b0; inc_long = 1'b0; inc_crc = 1'b0;
        inc_rep = 1'b0; inc_ooo = 1'b0; inc_tle = 1'b0;
        ev_reply = 1'b0; ev_seq_take = 1'b0; ev_exec = 1'b0;
        ev_status = 3'd0;
        if (rx_n < 6'd4) begin
            inc_short = 1'b1;
        end else if (e_long) begin
            inc_long = 1'b1;
        end else if (e_short2) begin
            inc_short = 1'b1;
        end else if (e_crc) begin
            inc_crc = 1'b1;
        end else begin
            ev_reply = 1'b1;
            if (!known) begin
                ev_status = 3'd1; inc_tle = 1'b1;
            end else if (e_len) begin
                ev_status = 3'd2; inc_tle = 1'b1;
            end else if (e_seqbad) begin
                ev_status = 3'd4;
                if (d_zero) inc_rep = 1'b1; else inc_ooo = 1'b1;
            end else begin
                ev_seq_take = 1'b1;
                if (e_regbad) begin
                    ev_status = 3'd3; inc_tle = 1'b1;
                end else if (e_ro) begin
                    ev_status = 3'd5; inc_tle = 1'b1;
                end else begin
                    ev_exec = 1'b1;
                end
            end
        end
    end
    wire inc_any = inc_short | inc_long | inc_crc | inc_rep | inc_ooo | inc_tle;

    logic [31:0] rval;
    always_comb begin
        case (rg[2:0])
            3'd0:    rval = ID_WORD;
            3'd1:    rval = scr1;
            3'd2:    rval = scr2;
            3'd3:    rval = scr3;
            3'd4:    rval = cmds;
            3'd5:    rval = refused;
            3'd6:    rval = {16'b0, period};
            default: rval = uptime;
        endcase
    end

    wire [15:0] start_p = {rxb[4], rxb[5]};
    wire [31:0] wr_val  = {rxb[5], rxb[6], rxb[7], rxb[8]};   // four bytes after the register number

    // ---------------------------------------------------------------- ticks
    wire        tick     = (pending != 16'd0);
    wire [15:0] pend_dec = pending - {15'b0, tick};
    wire [16:0] pend_sum = {1'b0, pend_dec} + {9'b0, win_wdata[7:0]};
    wire [31:0] uptime_nx = uptime + 32'd1;
    wire [16:0] tcount_nx = {1'b0, tcount} + 17'd1;
    wire        due = tel_on && tick && (tcount_nx == {1'b0, period});

    // ---------------------------------------------------------------- main sequential block
    always_ff @(posedge clk) begin
        if (rst) begin
            rx_crc <= CRC_INIT; rx_n <= 6'd0; ev_pend <= 1'b0;
            cmds <= 32'd0; refused <= 32'd0; uptime <= 32'd0;
            c_crc <= 16'd0; c_short <= 16'd0; c_long <= 16'd0;
            c_rep <= 16'd0; c_ooo <= 16'd0; c_tle <= 16'd0;
            scr1 <= 32'd0; scr2 <= 32'd0; scr3 <= 32'd0;
            last_seq <= 16'd0; seq_valid <= 1'b0;
            period <= 16'(DEFAULT_PERIOD); tcount <= 16'd0;
            tel_on <= 1'b0; held <= 1'b0; fseq <= 16'd0; fcount <= 16'd0;
            pending <= 16'd0; ridx <= 7'd0; tidx <= 7'd0;
            rep_len <= 6'd0; b_state <= B_IDLE; bidx <= 5'd0; blen <= 5'd0; bcrc <= CRC_INIT;
            f_state <= 2'd0; fidx <= 5'd0; fcrc <= CRC_INIT;
        end else begin
            // ---- window writes
            if (wr_ridx) ridx <= win_wdata[6:0];
            if (wr_tidx) tidx <= win_wdata[6:0];
            pending <= wr_tick ? (pend_sum[16] ? 16'hFFFF : pend_sum[15:0]) : pend_dec;

            // ---- input byte capture
            if (wr_in) begin
                rx_crc <= rx_crc_nx;
                if (rx_n != 6'd63) rx_n <= rx_n + 6'd1;
                if (win_wdata[8]) ev_pend <= 1'b1;
            end

            // ---- tick: uptime and telemetry timing
            if (tick) begin
                uptime <= uptime_nx;
                if (tel_on) tcount <= tcount_nx[15:0];
            end
            if (due) begin
                tcount <= 16'd0;
                if (!held) begin
                    held <= 1'b1;
                    fseq <= fseq + 16'd1;
                    fcount <= fcount + 16'd1;
                    f_state <= 2'd1; fidx <= 5'd0; fcrc <= CRC_INIT;
                end
            end

            // ---- frame crc engine
            case (f_state)
                2'd1: begin
                    fcrc <= f_crc_nx;
                    if (fidx == 5'd12) begin f_state <= 2'd2; fidx <= 5'd13; end
                    else fidx <= fidx + 5'd1;
                end
                2'd2: begin
                    fcrc <= {8'h00, fcrc[31:8]};
                    fidx <= fidx + 5'd1;
                    if (fidx == 5'd16) f_state <= 2'd0;
                end
                default: ;
            endcase

            // ---- reply crc engine
            case (b_state)
                B_CRC: begin
                    bcrc <= b_crc_nx;
                    if (bidx == blen - 5'd1) begin b_state <= B_TRL; bidx <= blen; end
                    else bidx <= bidx + 5'd1;
                end
                B_TRL: begin
                    bcrc <= {8'h00, bcrc[31:8]};
                    bidx <= bidx + 5'd1;
                    if (bidx == blen + 5'd3) begin
                        b_state <= B_IDLE;
                        rep_len <= {1'b0, blen} + 6'd4;
                    end
                end
                default: ;
            endcase

            // ---- take releases the held frame
            if (wr_take) begin held <= 1'b0; f_state <= 2'd0; end

            // ---- evaluation of the captured packet
            if (ev_pend) begin
                ev_pend <= 1'b0;
                rx_crc <= CRC_INIT; rx_n <= 6'd0;
                rep_len <= 6'd0;
                if (inc_any) refused <= refused + 32'd1;
                if (inc_short) c_short <= c_short + 16'd1;
                if (inc_long)  c_long  <= c_long + 16'd1;
                if (inc_crc)   c_crc   <= c_crc + 16'd1;
                if (inc_rep)   c_rep   <= c_rep + 16'd1;
                if (inc_ooo)   c_ooo   <= c_ooo + 16'd1;
                if (inc_tle)   c_tle   <= c_tle + 16'd1;
                if (ev_seq_take) begin last_seq <= sq; seq_valid <= 1'b1; end
                if (ev_exec) begin
                    cmds <= cmds + 32'd1;
                    case (ty)
                        8'd2: begin
                            case (rg[1:0])
                                2'd1: scr1 <= wr_val;
                                2'd2: scr2 <= wr_val;
                                default: scr3 <= wr_val;
                            endcase
                        end
                        8'd4: begin
                            if (start_p != 16'd0)
                                period <= (start_p < 16'(MIN_PERIOD)) ? 16'(MIN_PERIOD) : start_p;
                            tel_on <= 1'b1;
                            tcount <= 16'd0;
                        end
                        8'd5: begin
                            tel_on <= 1'b0;
                            held <= 1'b0;
                            f_state <= 2'd0;
                        end
                        default: ;
                    endcase
                end
                if (ev_reply) begin
                    b_state <= B_CRC; bidx <= 5'd0; bcrc <= CRC_INIT;
                    blen <= (ev_exec && ty == 8'd1) ? 5'd9 :
                            (ev_exec && ty == 8'd3) ? 5'd22 : 5'd5;
                end
            end
        end
    end

    // ---------------------------------------------------------------- buffers (no reset)
    always_ff @(posedge clk) begin
        if (wr_in && (rx_n < 6'd10)) rxb[rx_n[3:0]] <= win_wdata[7:0];

        // telemetry frame, loaded at the due moment
        if (due && !held) begin
            fb[0]  <= 8'hC0;
            fb[1]  <= 8'h00;
            fb[2]  <= fseq[15:8];
            fb[3]  <= fseq[7:0];
            fb[4]  <= 8'd8;
            fb[5]  <= uptime_nx[31:24];
            fb[6]  <= uptime_nx[23:16];
            fb[7]  <= uptime_nx[15:8];
            fb[8]  <= uptime_nx[7:0];
            fb[9]  <= cmds[15:8];
            fb[10] <= cmds[7:0];
            fb[11] <= refused[15:8];
            fb[12] <= refused[7:0];
        end else if (f_state == 2'd2) begin
            fb[fidx] <= ~fcrc[7:0];
        end

        // reply: header and payload loaded at evaluation, trailer written by the crc engine
        if (ev_pend && ev_reply) begin
            rb[0] <= ty | 8'h80;
            rb[1] <= {5'b0, ev_status};
            rb[2] <= sq[15:8];
            rb[3] <= sq[7:0];
            rb[4] <= (ev_exec && ty == 8'd1) ? 8'd4 : (ev_exec && ty == 8'd3) ? 8'd17 : 8'd0;
            rb[5]  <= (ty == 8'd1) ? rval[31:24] : cmds[15:8];
            rb[6]  <= (ty == 8'd1) ? rval[23:16] : cmds[7:0];
            rb[7]  <= (ty == 8'd1) ? rval[15:8]  : c_crc[15:8];
            rb[8]  <= (ty == 8'd1) ? rval[7:0]   : c_crc[7:0];
            rb[9]  <= c_short[15:8];
            rb[10] <= c_short[7:0];
            rb[11] <= c_long[15:8];
            rb[12] <= c_long[7:0];
            rb[13] <= c_rep[15:8];
            rb[14] <= c_rep[7:0];
            rb[15] <= c_ooo[15:8];
            rb[16] <= c_ooo[7:0];
            rb[17] <= c_tle[15:8];
            rb[18] <= c_tle[7:0];
            rb[19] <= fcount[15:8];
            rb[20] <= fcount[7:0];
            rb[21] <= {7'b0, tel_on};
        end else if (b_state == B_TRL) begin
            rb[bidx] <= ~bcrc[7:0];
        end
    end

    // ---------------------------------------------------------------- readback
    logic [31:0] rword, tword;
    logic [9:0]  ridx_b, tidx_b, ri, ti;
    always_comb begin
        ridx_b = {1'b0, ridx, 2'b00};
        tidx_b = {1'b0, tidx, 2'b00};
        rword = 32'd0;
        tword = 32'd0;
        ri = 10'd0;
        ti = 10'd0;
        for (int j = 0; j < 4; j++) begin
            ri = ridx_b + 10'(j);
            ti = tidx_b + 10'(j);
            rword[31 - 8 * j -: 8] = (ri < {4'b0, rep_len}) ? rb[ri[4:0]] : 8'h00;
            tword[31 - 8 * j -: 8] = (held && (ti < 10'd17)) ? fb[ti[4:0]] : 8'h00;
        end
    end

    wire busy = ev_pend || (b_state != B_IDLE) || (pending != 16'd0);

    always_ff @(posedge clk) begin
        if (rst) begin
            win_rdata <= 32'd0;
        end else begin
            case (win_addr)
                7'd2:    win_rdata <= {26'b0, rep_len};
                7'd3:    win_rdata <= {25'b0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= held ? 32'd17 : 32'd0;
                7'd6:    win_rdata <= {25'b0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'b0, busy, tel_on};
                default: win_rdata <= 32'd0;
            endcase
        end
    end

    assign led = cmds[15:0];

    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_ok;
    assign unused_ok = &{1'b0, win_wdata[31:9], b_crc_nx[0], f_crc_nx[0], rxb[9]};
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
