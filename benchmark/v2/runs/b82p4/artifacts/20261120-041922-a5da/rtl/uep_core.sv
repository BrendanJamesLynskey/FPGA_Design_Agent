// uep_core: packet judge, command executor, reply builder, telemetry and register window.
// Single clock. Synchronous active-high reset. Packet bytes are collected, then judged
// serially (byte-wise CRC-32), then the reply is built and its CRC computed serially.
module uep_core #(
    parameter logic [31:0] ID_WORD      = 32'h55445031,
    parameter int          PERIOD_RESET = 100,
    parameter int          PERIOD_MIN   = 4
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
    typedef enum logic [2:0] {S_IDLE, S_CLASS, S_CRC, S_CHK, S_EXEC, S_BCRC} st_t;
    st_t st;

    // CRC-32 (reflected 0xEDB88320), one byte per call, register form (no final inversion)
    function automatic logic [31:0] crc8(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] r;
        r = c ^ {24'h0, d};
        for (int i = 0; i < 8; i++) r = r[0] ? ((r >> 1) ^ 32'hEDB88320) : (r >> 1);
        return r;
    endfunction

    // ---------------------------------------------------------------- state
    logic [7:0]  pb [0:15];       // packet bytes
    logic [4:0]  cnt;             // bytes received (saturating)
    logic [31:0] crc;
    logic [4:0]  ci;
    logic [7:0]  rb [0:31];       // reply buffer (26 used)
    logic [5:0]  rlen;
    logic [4:0]  bl;

    logic [15:0] c_cmd, c_bad, c_short, c_long, c_rep, c_ooo, c_err, c_ref;
    logic [31:0] scr1, scr2, scr3;
    logic [15:0] last_seq;
    logic        have_last;

    logic        tel_on;
    logic [15:0] period, tcount, fseq, fcount;
    logic [31:0] ticks;
    logic [8:0]  pend;
    logic        held, tbusy;
    logic [7:0]  tb [0:31];       // telemetry frame (17 used)
    logic [31:0] tcrc;
    logic [4:0]  ti;

    logic [6:0]  ridx, tidx;

    // ---------------------------------------------------------------- window decode
    wire wr_in   = win_wr && (win_addr == 7'd0);
    wire wr_tick = win_wr && (win_addr == 7'd1);
    wire wr_ridx = win_wr && (win_addr == 7'd3);
    wire wr_tidx = win_wr && (win_addr == 7'd6);
    wire wr_take = win_wr && (win_addr == 7'd8);

    // ---------------------------------------------------------------- tick generator
    wire        tick   = (pend != 9'd0);
    wire [16:0] tc_nxt = {1'b0, tcount} + 17'd1;
    wire        due    = tick && tel_on && (tc_nxt == {1'b0, period});
    wire [31:0] ticks_n = ticks + 32'd1;

    // serial CRC engines (next values)
    wire [31:0] cn_t = crc8(tcrc, tb[ti]);
    wire [31:0] cn_b = crc8(crc, rb[ci]);

    // ---------------------------------------------------------------- execute-stage decode
    wire [7:0]  e_typ = pb[0];
    wire [7:0]  e_ln  = pb[1];
    wire [15:0] e_seq = {pb[2], pb[3]};
    wire [15:0] e_reg = {pb[4], pb[5]};
    wire [15:0] e_per = {pb[4], pb[5]};
    wire [15:0] seq_d = e_seq - last_seq;
    wire        seq_ok = !have_last || ((seq_d != 16'd0) && !seq_d[15]);
    wire        typ_ok = (e_typ >= 8'd1) && (e_typ <= 8'd5);
    logic [7:0] exp_len;
    always_comb begin
        case (e_typ)
            8'd1:    exp_len = 8'd2;
            8'd2:    exp_len = 8'd6;
            8'd4:    exp_len = 8'd2;
            default: exp_len = 8'd0;
        endcase
    end
    wire len_ok  = (e_ln == exp_len);
    wire is_rw   = (e_typ == 8'd1) || (e_typ == 8'd2);
    wire reg_hi  = |e_reg[15:3];
    wire ro_wr   = (e_typ == 8'd2) && ((e_reg[2:0] == 3'd0) || e_reg[2]);
    logic [2:0] ex_status;
    always_comb begin
        if (!typ_ok)               ex_status = 3'd1;
        else if (!len_ok)          ex_status = 3'd2;
        else if (!seq_ok)          ex_status = 3'd4;
        else if (is_rw && reg_hi)  ex_status = 3'd3;
        else if (ro_wr)            ex_status = 3'd5;
        else                       ex_status = 3'd0;
    end

    logic [31:0] rd_val;
    always_comb begin
        case (e_reg[2:0])
            3'd0:    rd_val = ID_WORD;
            3'd1:    rd_val = scr1;
            3'd2:    rd_val = scr2;
            3'd3:    rd_val = scr3;
            3'd4:    rd_val = {16'h0, c_cmd};
            3'd5:    rd_val = {16'h0, c_ref};
            3'd6:    rd_val = {16'h0, period};
            default: rd_val = ticks;
        endcase
    end
    wire [135:0] sp = {c_cmd, c_bad, c_short, c_long, c_rep, c_ooo, c_err, fcount, 7'h0, tel_on};
    wire [31:0]  wval = {pb[6], pb[7], pb[8], pb[9]};

    // ---------------------------------------------------------------- read mux
    wire busy = (st != S_IDLE) || tbusy;
    wire [5:0] tlen = (held && !tbusy) ? 6'd17 : 6'd0;

    logic [31:0] rword, tword;
    always_comb begin
        logic [8:0] j;
        for (int k = 0; k < 4; k++) begin
            j = {ridx, 2'b00} + 9'(k);
            rword[31 - 8*k -: 8] = (j < {3'b000, rlen}) ? rb[j[4:0]] : 8'h00;
            j = {tidx, 2'b00} + 9'(k);
            tword[31 - 8*k -: 8] = (j < {3'b000, tlen}) ? tb[j[4:0]] : 8'h00;
        end
    end

    logic [31:0] rd_mux;
    always_comb begin
        case (win_addr)
            7'd2:    rd_mux = {26'h0, rlen};
            7'd3:    rd_mux = {25'h0, ridx};
            7'd4:    rd_mux = rword;
            7'd5:    rd_mux = {26'h0, tlen};
            7'd6:    rd_mux = {25'h0, tidx};
            7'd7:    rd_mux = tword;
            7'd9:    rd_mux = {30'h0, busy, tel_on};
            default: rd_mux = 32'h0;
        endcase
    end

    assign led = c_cmd;

    // ---------------------------------------------------------------- main sequential logic
    always_ff @(posedge clk) begin
        if (rst) begin
            st        <= S_IDLE;
            cnt       <= 5'd0;
            rlen      <= 6'd0;
            c_cmd     <= 16'd0;
            c_bad     <= 16'd0;
            c_short   <= 16'd0;
            c_long    <= 16'd0;
            c_rep     <= 16'd0;
            c_ooo     <= 16'd0;
            c_err     <= 16'd0;
            c_ref     <= 16'd0;
            scr1      <= 32'd0;
            scr2      <= 32'd0;
            scr3      <= 32'd0;
            have_last <= 1'b0;
            tel_on    <= 1'b0;
            period    <= 16'(PERIOD_RESET);
            tcount    <= 16'd0;
            fseq      <= 16'd0;
            fcount    <= 16'd0;
            ticks     <= 32'd0;
            pend      <= 9'd0;
            held      <= 1'b0;
            tbusy     <= 1'b0;
            ridx      <= 7'd0;
            tidx      <= 7'd0;
            win_rdata <= 32'd0;
        end else begin
            // ---- window
            if (win_rd)   win_rdata <= rd_mux;
            if (wr_ridx)  ridx <= win_wdata[6:0];
            if (wr_tidx)  tidx <= win_wdata[6:0];
            pend <= pend - {8'h0, tick} + {1'b0, (wr_tick ? win_wdata[7:0] : 8'h00)};

            // ---- ticks and telemetry due
            if (tick) begin
                ticks <= ticks_n;
                if (tel_on) begin
                    if (due) begin
                        tcount <= 16'd0;
                        if (!held) begin
                            held   <= 1'b1;
                            tbusy  <= 1'b1;
                            fseq   <= fseq + 16'd1;
                            fcount <= fcount + 16'd1;
                            tcrc   <= 32'hFFFFFFFF;
                            ti     <= 5'd0;
                            tb[0]  <= 8'hC0;
                            tb[1]  <= 8'h00;
                            tb[2]  <= fseq[15:8];
                            tb[3]  <= fseq[7:0];
                            tb[4]  <= 8'd8;
                            tb[5]  <= ticks_n[31:24];
                            tb[6]  <= ticks_n[23:16];
                            tb[7]  <= ticks_n[15:8];
                            tb[8]  <= ticks_n[7:0];
                            tb[9]  <= c_cmd[15:8];
                            tb[10] <= c_cmd[7:0];
                            tb[11] <= c_ref[15:8];
                            tb[12] <= c_ref[7:0];
                        end
                    end else begin
                        tcount <= tc_nxt[15:0];
                    end
                end
            end

            // ---- frame CRC
            if (tbusy) begin
                tcrc <= cn_t;
                ti   <= ti + 5'd1;
                if (ti == 5'd12) begin
                    tb[13] <= ~cn_t[7:0];
                    tb[14] <= ~cn_t[15:8];
                    tb[15] <= ~cn_t[23:16];
                    tb[16] <= ~cn_t[31:24];
                    tbusy  <= 1'b0;
                end
            end

            // ---- packet state machine
            case (st)
                S_IDLE: begin
                    if (wr_in) begin
                        if (cnt < 5'd16) pb[cnt[3:0]] <= win_wdata[7:0];
                        if (cnt != 5'd31) cnt <= cnt + 5'd1;
                        if (win_wdata[8]) begin
                            st   <= S_CLASS;
                            rlen <= 6'd0;
                        end
                    end
                end
                S_CLASS: begin
                    if (cnt < 5'd4) begin
                        c_short <= c_short + 16'd1;
                        c_ref   <= c_ref + 16'd1;
                        cnt     <= 5'd0;
                        st      <= S_IDLE;
                    end else if ((e_ln > 8'd8) || ({4'h0, cnt} > (9'd8 + {1'b0, e_ln}))) begin
                        c_long <= c_long + 16'd1;
                        c_ref  <= c_ref + 16'd1;
                        cnt    <= 5'd0;
                        st     <= S_IDLE;
                    end else if ({4'h0, cnt} < (9'd8 + {1'b0, e_ln})) begin
                        c_short <= c_short + 16'd1;
                        c_ref   <= c_ref + 16'd1;
                        cnt     <= 5'd0;
                        st      <= S_IDLE;
                    end else begin
                        crc <= 32'hFFFFFFFF;
                        ci  <= 5'd0;
                        st  <= S_CRC;
                    end
                end
                S_CRC: begin
                    crc <= crc8(crc, pb[ci[3:0]]);
                    ci  <= ci + 5'd1;
                    if ((ci + 5'd1) == cnt) st <= S_CHK;
                end
                S_CHK: begin
                    if (crc == 32'hDEBB20E3) begin
                        st <= S_EXEC;
                    end else begin
                        c_bad <= c_bad + 16'd1;
                        c_ref <= c_ref + 16'd1;
                        cnt   <= 5'd0;
                        st    <= S_IDLE;
                    end
                end
                S_EXEC: begin
                    logic [4:0] plen;
                    plen = 5'd0;
                    rb[0] <= e_typ | 8'h80;
                    rb[1] <= {5'h0, ex_status};
                    rb[2] <= pb[2];
                    rb[3] <= pb[3];
                    if (ex_status != 3'd4 && ex_status != 3'd1 && ex_status != 3'd2) begin
                        last_seq  <= e_seq;
                        have_last <= 1'b1;
                    end
                    if (ex_status == 3'd0) begin
                        c_cmd <= c_cmd + 16'd1;
                        case (e_typ)
                            8'd1: begin
                                plen  = 5'd4;
                                rb[5] <= rd_val[31:24];
                                rb[6] <= rd_val[23:16];
                                rb[7] <= rd_val[15:8];
                                rb[8] <= rd_val[7:0];
                            end
                            8'd2: begin
                                case (e_reg[1:0])
                                    2'd1:    scr1 <= wval;
                                    2'd2:    scr2 <= wval;
                                    default: scr3 <= wval;
                                endcase
                            end
                            8'd3: begin
                                plen = 5'd17;
                                for (int i = 0; i < 17; i++) rb[5 + i] <= sp[135 - 8*i -: 8];
                            end
                            8'd4: begin
                                if (e_per != 16'd0)
                                    period <= (e_per < 16'(PERIOD_MIN)) ? 16'(PERIOD_MIN) : e_per;
                                tel_on <= 1'b1;
                                tcount <= 16'd0;
                            end
                            default: begin   // 5: stop
                                tel_on <= 1'b0;
                                held   <= 1'b0;
                                tbusy  <= 1'b0;
                            end
                        endcase
                    end else begin
                        c_ref <= c_ref + 16'd1;
                        if (ex_status == 3'd4) begin
                            if (seq_d == 16'd0) c_rep <= c_rep + 16'd1;
                            else                c_ooo <= c_ooo + 16'd1;
                        end else begin
                            c_err <= c_err + 16'd1;
                        end
                    end
                    rb[4] <= {3'h0, plen};
                    bl    <= 5'd5 + plen;
                    crc   <= 32'hFFFFFFFF;
                    ci    <= 5'd0;
                    st    <= S_BCRC;
                end
                S_BCRC: begin
                    crc <= cn_b;
                    ci  <= ci + 5'd1;
                    if ((ci + 5'd1) == bl) begin
                        rb[bl]          <= ~cn_b[7:0];
                        rb[bl + 5'd1]   <= ~cn_b[15:8];
                        rb[bl + 5'd2]   <= ~cn_b[23:16];
                        rb[bl + 5'd3]   <= ~cn_b[31:24];
                        rlen            <= {1'b0, bl} + 6'd4;
                        cnt             <= 5'd0;
                        st              <= S_IDLE;
                    end
                end
                default: st <= S_IDLE;
            endcase

            // ---- take frees the held frame
            if (wr_take) begin
                held  <= 1'b0;
                tbusy <= 1'b0;
            end
        end
    end
endmodule
