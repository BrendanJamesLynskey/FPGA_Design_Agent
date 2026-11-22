// uep_core: command parser, executor, reply builder, telemetry and register window.
// Single clock, synchronous active-high reset. Three CRC-32 byte engines (receive, reply, frame).
module uep_core #(
    parameter logic [31:0] ID_WORD        = 32'h55445031,
    parameter int unsigned DEFAULT_PERIOD = 100,
    parameter int unsigned MIN_PERIOD     = 4
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    localparam logic [31:0] CRC_RESIDUE = 32'hDEBB20E3;
    localparam logic [31:0] CRC_INIT    = 32'hFFFFFFFF;

    // decision classes
    localparam logic [3:0] C_SHORT = 4'd0, C_LONG = 4'd1, C_CRC = 4'd2, C_TYPE = 4'd3,
                           C_LEN = 4'd4, C_REP = 4'd5, C_OOO = 4'd6, C_REG = 4'd7,
                           C_ACC = 4'd8, C_OK = 4'd9;
    // builder states
    localparam logic [1:0] B_IDLE = 2'd0, B_FEED = 2'd1, B_PUT = 2'd2;

    // ---------------- receive pipeline
    logic        in_v, in_e, dec;
    logic [7:0]  in_b;
    logic [5:0]  n;
    logic [7:0]  pkt [0:9];
    logic [31:0] rx_crc, rx_crc_n;

    crc32_byte u_crc_rx (.c(rx_crc), .d(in_b), .n(rx_crc_n));

    // ---------------- architectural state
    logic [31:0] cmds, refused;
    logic [15:0] c_crc, c_short, c_long, c_rep, c_ooo, c_err;
    logic [15:0] last_seq;
    logic        have_last;
    logic [31:0] s1, s2, s3;
    logic [15:0] period, phase, fseq, fcount;
    logic        tel_on, held;
    logic [31:0] uptime;
    logic [7:0]  pending;
    logic [6:0]  ridx, tidx;

    // ---------------- reply / frame buffers
    logic [7:0]  rbuf [0:27];
    logic [5:0]  rlen;
    logic [7:0]  tbuf [0:16];
    logic [1:0]  rs, ts;
    logic [4:0]  ri, ti, rtotal;
    logic [31:0] r_crc, r_crc_n, t_crc, t_crc_n;

    crc32_byte u_crc_rp (.c(r_crc), .d(rbuf[ri]), .n(r_crc_n));
    crc32_byte u_crc_tf (.c(t_crc), .d(tbuf[ti]), .n(t_crc_n));

    // ---------------- decision (combinational on the stored packet)
    logic [7:0]  d_typ, d_len;
    logic [15:0] d_seq, d_diff, d_reg;
    logic [7:0]  d_want;
    logic [5:0]  d_max;
    logic [3:0]  cls;
    logic [2:0]  st;
    logic [4:0]  d_plen;
    logic [31:0] rd_val, wr_val;
    logic [15:0] sv [0:7];

    always_comb begin
        d_typ  = pkt[0];
        d_len  = pkt[1];
        d_seq  = {pkt[2], pkt[3]};
        d_reg  = {pkt[4], pkt[5]};
        d_diff = d_seq - last_seq;
        d_max  = 6'd8 + {2'b00, d_len[3:0]};
        wr_val = {pkt[6], pkt[7], pkt[8], pkt[9]};
        case (d_typ)
            8'd1:    d_want = 8'd2;
            8'd2:    d_want = 8'd6;
            8'd4:    d_want = 8'd2;
            default: d_want = 8'd0;
        endcase
        case (d_reg[2:0])
            3'd0:    rd_val = ID_WORD;
            3'd1:    rd_val = s1;
            3'd2:    rd_val = s2;
            3'd3:    rd_val = s3;
            3'd4:    rd_val = cmds;
            3'd5:    rd_val = refused;
            3'd6:    rd_val = {16'h0, period};
            default: rd_val = uptime;
        endcase
        sv[0] = cmds[15:0];
        sv[1] = c_crc;
        sv[2] = c_short;
        sv[3] = c_long;
        sv[4] = c_rep;
        sv[5] = c_ooo;
        sv[6] = c_err;
        sv[7] = fcount;

        cls = C_OK;
        st  = 3'd0;
        if (n < 6'd4) begin
            cls = C_SHORT;
        end else if (d_len > 8'd8 || n > d_max) begin
            cls = C_LONG;
        end else if (n < d_max) begin
            cls = C_SHORT;
        end else if (rx_crc != CRC_RESIDUE) begin
            cls = C_CRC;
        end else if (d_typ == 8'd0 || d_typ > 8'd5) begin
            cls = C_TYPE;
            st  = 3'd1;
        end else if (d_len != d_want) begin
            cls = C_LEN;
            st  = 3'd2;
        end else if (have_last && d_diff == 16'd0) begin
            cls = C_REP;
            st  = 3'd4;
        end else if (have_last && d_diff[15]) begin
            cls = C_OOO;
            st  = 3'd4;
        end else if ((d_typ == 8'd1 || d_typ == 8'd2) && d_reg[15:3] != 13'd0) begin
            cls = C_REG;
            st  = 3'd3;
        end else if (d_typ == 8'd2 && (d_reg[2] || d_reg[2:0] == 3'd0)) begin
            cls = C_ACC;
            st  = 3'd5;
        end
        d_plen = 5'd0;
        if (cls == C_OK) begin
            if (d_typ == 8'd1) d_plen = 5'd4;
            if (d_typ == 8'd3) d_plen = 5'd17;
        end
    end

    // ---------------- tick source
    logic        tick;
    logic [31:0] up_next;
    logic [16:0] phase_n;
    assign tick    = (pending != 8'd0);
    assign up_next = uptime + 32'd1;
    assign phase_n = {1'b0, phase} + 17'd1;

    // ---------------- main sequential block
    always_ff @(posedge clk) begin
        if (rst) begin
            in_v <= 1'b0; in_e <= 1'b0; in_b <= 8'h0; dec <= 1'b0;
            n <= 6'd0; rx_crc <= CRC_INIT;
            cmds <= 32'h0; refused <= 32'h0;
            c_crc <= 16'h0; c_short <= 16'h0; c_long <= 16'h0;
            c_rep <= 16'h0; c_ooo <= 16'h0; c_err <= 16'h0;
            last_seq <= 16'h0; have_last <= 1'b0;
            s1 <= 32'h0; s2 <= 32'h0; s3 <= 32'h0;
            period <= 16'(DEFAULT_PERIOD); phase <= 16'h0;
            fseq <= 16'h0; fcount <= 16'h0;
            tel_on <= 1'b0; held <= 1'b0;
            uptime <= 32'h0; pending <= 8'h0;
            ridx <= 7'h0; tidx <= 7'h0;
            rlen <= 6'h0; rs <= B_IDLE; ts <= B_IDLE;
            ri <= 5'h0; ti <= 5'h0; rtotal <= 5'h0;
            r_crc <= CRC_INIT; t_crc <= CRC_INIT;
        end else begin
            // ---- window writes
            in_v <= 1'b0;
            if (win_wr) begin
                case (win_addr)
                    7'd0: begin
                        in_v <= 1'b1;
                        in_b <= win_wdata[7:0];
                        in_e <= win_wdata[8];
                    end
                    7'd1: pending <= win_wdata[7:0];
                    7'd3: ridx <= win_wdata[6:0];
                    7'd6: tidx <= win_wdata[6:0];
                    default: ;
                endcase
            end
            if (!(win_wr && win_addr == 7'd1) && tick) pending <= pending - 8'd1;

            // ---- stage B: absorb one packet byte
            if (in_v) begin
                rx_crc <= rx_crc_n;
                if (n < 6'd10) pkt[n[3:0]] <= in_b;
                if (n != 6'd63) n <= n + 6'd1;
                if (in_e) dec <= 1'b1;
            end

            // ---- ticks, uptime, telemetry due
            if (tick) begin
                uptime <= up_next;
                if (tel_on) begin
                    if (phase_n >= {1'b0, period}) begin
                        phase <= 16'h0;
                        if (!held) begin
                            held   <= 1'b1;
                            fseq   <= fseq + 16'd1;
                            fcount <= fcount + 16'd1;
                            tbuf[0]  <= 8'hC0;
                            tbuf[1]  <= 8'h00;
                            tbuf[2]  <= fseq[15:8];
                            tbuf[3]  <= fseq[7:0];
                            tbuf[4]  <= 8'h08;
                            tbuf[5]  <= up_next[31:24];
                            tbuf[6]  <= up_next[23:16];
                            tbuf[7]  <= up_next[15:8];
                            tbuf[8]  <= up_next[7:0];
                            tbuf[9]  <= cmds[15:8];
                            tbuf[10] <= cmds[7:0];
                            tbuf[11] <= refused[15:8];
                            tbuf[12] <= refused[7:0];
                            t_crc    <= CRC_INIT;
                            ti       <= 5'd0;
                            ts       <= B_FEED;
                        end
                    end else begin
                        phase <= phase_n[15:0];
                    end
                end
            end

            // ---- frame builder
            case (ts)
                B_FEED: begin
                    t_crc <= t_crc_n;
                    if (ti == 5'd12) begin
                        ts <= B_PUT;
                        ti <= 5'd0;
                    end else begin
                        ti <= ti + 5'd1;
                    end
                end
                B_PUT: begin
                    tbuf[5'd13 + ti] <= ~t_crc[{ti[1:0], 3'b000} +: 8];
                    if (ti == 5'd3) ts <= B_IDLE;
                    ti <= ti + 5'd1;
                end
                default: ;
            endcase

            // ---- reply builder
            case (rs)
                B_FEED: begin
                    r_crc <= r_crc_n;
                    if (ri == rtotal - 5'd1) begin
                        rs <= B_PUT;
                        ri <= 5'd0;
                    end else begin
                        ri <= ri + 5'd1;
                    end
                end
                B_PUT: begin
                    rbuf[rtotal + ri] <= ~r_crc[{ri[1:0], 3'b000} +: 8];
                    if (ri == 5'd3) begin
                        rs   <= B_IDLE;
                        rlen <= {1'b0, rtotal} + 6'd4;
                    end
                    ri <= ri + 5'd1;
                end
                default: ;
            endcase

            // ---- take register
            if (win_wr && win_addr == 7'd8) begin
                held <= 1'b0;
                ts   <= B_IDLE;
            end

            // ---- stage C: decision on the whole packet
            if (dec) begin
                dec    <= 1'b0;
                n      <= 6'd0;
                rx_crc <= CRC_INIT;
                rlen   <= 6'd0;
                if (cls != C_OK) refused <= refused + 32'd1;
                case (cls)
                    C_SHORT: c_short <= c_short + 16'd1;
                    C_LONG:  c_long  <= c_long + 16'd1;
                    C_CRC:   c_crc   <= c_crc + 16'd1;
                    C_TYPE, C_LEN, C_REG, C_ACC: c_err <= c_err + 16'd1;
                    C_REP:   c_rep   <= c_rep + 16'd1;
                    C_OOO:   c_ooo   <= c_ooo + 16'd1;
                    default: ;
                endcase
                if (cls == C_REG || cls == C_ACC || cls == C_OK) begin
                    last_seq  <= d_seq;
                    have_last <= 1'b1;
                end
                if (cls != C_SHORT && cls != C_LONG && cls != C_CRC) begin
                    rbuf[0] <= {1'b1, d_typ[6:0]};
                    rbuf[1] <= {5'b0, st};
                    rbuf[2] <= d_seq[15:8];
                    rbuf[3] <= d_seq[7:0];
                    rbuf[4] <= {3'b0, d_plen};
                    rs      <= B_FEED;
                    ri      <= 5'd0;
                    r_crc   <= CRC_INIT;
                    rtotal  <= 5'd5 + d_plen;
                end
                if (cls == C_OK) begin
                    cmds <= cmds + 32'd1;
                    case (d_typ)
                        8'd1: begin
                            rbuf[5] <= rd_val[31:24];
                            rbuf[6] <= rd_val[23:16];
                            rbuf[7] <= rd_val[15:8];
                            rbuf[8] <= rd_val[7:0];
                        end
                        8'd2: begin
                            case (d_reg[1:0])
                                2'd1: s1 <= wr_val;
                                2'd2: s2 <= wr_val;
                                default: s3 <= wr_val;
                            endcase
                        end
                        8'd3: begin
                            for (int j = 0; j < 8; j++) begin
                                rbuf[5 + 2 * j] <= sv[j][15:8];
                                rbuf[6 + 2 * j] <= sv[j][7:0];
                            end
                            rbuf[21] <= {7'b0, tel_on};
                        end
                        8'd4: begin
                            if (d_reg != 16'd0)
                                period <= (d_reg < 16'(MIN_PERIOD)) ? 16'(MIN_PERIOD) : d_reg;
                            tel_on <= 1'b1;
                            phase  <= 16'h0;
                        end
                        default: begin   // 5: stop
                            tel_on <= 1'b0;
                            held   <= 1'b0;
                            ts     <= B_IDLE;
                        end
                    endcase
                end
            end
        end
    end

    // ---------------- readback
    logic        busy;
    logic [31:0] rword, tword;
    logic [5:0]  tlen;
    logic [8:0]  rb, tb, ix;

    assign busy = in_v | dec | (rs != B_IDLE) | (ts != B_IDLE);
    assign tlen = (held && ts == B_IDLE) ? 6'd17 : 6'd0;
    assign led  = cmds[15:0];

    always_comb begin
        rword = 32'h0;
        tword = 32'h0;
        rb = {ridx, 2'b00};
        tb = {tidx, 2'b00};
        ix = 9'h0;
        for (int k = 0; k < 4; k++) begin
            ix = rb + 9'(k);
            if (ix < {3'b0, rlen} && ix < 9'd28)
                rword[31 - 8 * k -: 8] = rbuf[ix[4:0]];
            ix = tb + 9'(k);
            if (ix < {3'b0, tlen} && ix < 9'd17)
                tword[31 - 8 * k -: 8] = tbuf[ix[4:0]];
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            win_rdata <= 32'h0;
        end else begin
            win_rdata <= 32'h0;
            if (win_rd) begin
                case (win_addr)
                    7'd2: win_rdata <= {26'h0, rlen};
                    7'd3: win_rdata <= {25'h0, ridx};
                    7'd4: win_rdata <= rword;
                    7'd5: win_rdata <= {26'h0, tlen};
                    7'd6: win_rdata <= {25'h0, tidx};
                    7'd7: win_rdata <= tword;
                    7'd9: win_rdata <= {30'h0, busy, tel_on};
                    default: ;
                endcase
            end
        end
    end
endmodule
