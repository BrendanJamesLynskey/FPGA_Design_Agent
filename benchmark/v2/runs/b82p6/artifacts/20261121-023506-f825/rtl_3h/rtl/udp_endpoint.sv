// udp_endpoint: packet parser, refusal rules, counters, device registers R0..R7, reply builder and the
// shell window registers. Bytes arrive through window register IN; the reply (at most 26 bytes) is read
// back as words through RIDX/RWORD; telemetry lives in the telemetry module.
module udp_endpoint #(
    parameter logic [31:0] ID_WORD        = 32'h5544_5031,
    parameter int          DEFAULT_PERIOD = 100,
    parameter int          MIN_PERIOD     = 4,
    parameter int          MAX_PAYLOAD    = 8
) (
    input  logic        clk,
    input  logic        rst,          // synchronous, active high
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,    // only bits 8:0 matter for IN, 7:0 for the others
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    localparam logic [31:0] CRC_RESIDUE = 32'hDEBB_20E3;

    typedef enum logic [1:0] {S_RX, S_EVAL, S_PASS, S_TRL} state_t;
    state_t state;

    // ---- packet capture
    logic [7:0]  n;                  // bytes received so far (saturating)
    logic [7:0]  b_type, b_len;
    logic [15:0] b_seq, last_seq;
    logic        have_last, busy;
    logic [7:0]  pbuf [0:7];         // packet bytes 4..11
    // ---- device registers and counters
    logic [31:0] scratch [0:2];
    logic [31:0] cmds, refused;
    logic [15:0] c_bad, c_short, c_long, c_rep, c_ooo, c_err;
    // ---- reply
    logic [7:0]  rbuf [0:31];
    logic [4:0]  rlen, rplen, k;
    logic [1:0]  t;
    logic [6:0]  ridx, tidx;
    logic [7:0]  pend;

    // ---- telemetry connection
    logic        tel_on, tel_start, tel_stop, tel_take, tick;
    logic [15:0] period, fcount;
    logic [31:0] ticks, tword;
    logic [4:0]  tlen;

    // ---- crc
    logic [31:0] crc;
    logic        crc_init, crc_en;
    logic [7:0]  crc_data;

    logic in_wr;
    assign in_wr = win_wr && (win_addr == 7'd0);
    assign led   = cmds[15:0];
    assign tick  = (pend != 8'd0);

    // ------------------------------------------------------------------ rule decode (used in S_EVAL)
    logic [8:0]  len9;
    logic [15:0] dseq, reg_no;
    logic [3:0]  need;
    logic        d_long, d_short, d_bad, typ_ok, len_ok, seq_ok, reg_bad, reg_ro;
    logic        d_drop, d_reply, d_seqtake, d_cmd, d_wr, d_stat_cnt;
    logic        r_bad, r_short, r_long, r_rep, r_ooo, r_err;
    logic [2:0]  d_status;
    logic [4:0]  d_plen;
    logic [31:0] rval;
    logic [135:0] pay_vec;

    assign len9    = {1'b0, b_len};
    assign dseq    = b_seq - last_seq;
    assign reg_no  = {pbuf[0], pbuf[1]};
    assign d_long  = (n >= 8'd4) && ((len9 > 9'(MAX_PAYLOAD)) || ({1'b0, n} > len9 + 9'd8));
    assign d_short = (n < 8'd4) || ({1'b0, n} < len9 + 9'd8);
    assign d_bad   = (crc != CRC_RESIDUE);
    assign typ_ok  = (b_type != 8'd0) && (b_type <= 8'd5);
    assign len_ok  = (len9 == {5'd0, need});
    assign seq_ok  = !have_last || ((dseq != 16'd0) && !dseq[15]);
    assign reg_bad = (reg_no[15:3] != 13'd0);
    assign reg_ro  = (reg_no[2:0] == 3'd0) || (reg_no[2:0] >= 3'd4);

    always_comb begin
        case (b_type)
            8'd1:    need = 4'd2;
            8'd2:    need = 4'd6;
            8'd4:    need = 4'd2;
            default: need = 4'd0;
        endcase
    end

    always_comb begin
        case (reg_no[2:0])
            3'd0:    rval = ID_WORD;
            3'd1:    rval = scratch[0];
            3'd2:    rval = scratch[1];
            3'd3:    rval = scratch[2];
            3'd4:    rval = cmds;
            3'd5:    rval = refused;
            3'd6:    rval = {16'd0, period};
            default: rval = ticks;
        endcase
    end

    always_comb begin
        d_drop    = 1'b0;
        d_status  = 3'd0;
        d_plen    = 5'd0;
        d_seqtake = 1'b0;
        d_cmd     = 1'b0;
        d_wr      = 1'b0;
        tel_start = 1'b0;
        tel_stop  = 1'b0;
        r_bad     = 1'b0;
        r_short   = 1'b0;
        r_long    = 1'b0;
        r_rep     = 1'b0;
        r_ooo     = 1'b0;
        r_err     = 1'b0;
        if (d_long) begin
            d_drop = 1'b1;
            r_long = 1'b1;
        end else if (d_short) begin
            d_drop  = 1'b1;
            r_short = 1'b1;
        end else if (d_bad) begin
            d_drop = 1'b1;
            r_bad  = 1'b1;
        end else if (!typ_ok) begin
            d_status = 3'd1;
            r_err    = 1'b1;
        end else if (!len_ok) begin
            d_status = 3'd2;
            r_err    = 1'b1;
        end else if (!seq_ok) begin
            d_status = 3'd4;
            r_rep    = (dseq == 16'd0);
            r_ooo    = (dseq != 16'd0);
        end else begin
            d_seqtake = 1'b1;
            if (((b_type == 8'd1) || (b_type == 8'd2)) && reg_bad) begin
                d_status = 3'd3;
                r_err    = 1'b1;
            end else if ((b_type == 8'd2) && reg_ro) begin
                d_status = 3'd5;
                r_err    = 1'b1;
            end else begin
                d_cmd = 1'b1;
                case (b_type)
                    8'd1:    d_plen = 5'd4;
                    8'd2:    d_wr = 1'b1;
                    8'd3:    d_plen = 5'd17;
                    8'd4:    tel_start = 1'b1;
                    default: tel_stop = 1'b1;
                endcase
            end
        end
        // the decisions only act in S_EVAL
        if (state != S_EVAL) begin
            d_seqtake = 1'b0;
            d_cmd     = 1'b0;
            d_wr      = 1'b0;
            tel_start = 1'b0;
            tel_stop  = 1'b0;
            r_bad     = 1'b0;
            r_short   = 1'b0;
            r_long    = 1'b0;
            r_rep     = 1'b0;
            r_ooo     = 1'b0;
            r_err     = 1'b0;
        end
        d_reply = !d_drop;
    end
    assign d_stat_cnt = r_bad | r_short | r_long | r_rep | r_ooo | r_err;

    assign pay_vec = (b_type == 8'd3)
        ? {cmds[15:0], c_bad, c_short, c_long, c_rep, c_ooo, c_err, fcount, 7'd0, tel_on}
        : {rval, 104'd0};

    // ------------------------------------------------------------------ control state
    always_ff @(posedge clk) begin
        if (rst) begin
            state     <= S_RX;
            n         <= 8'd0;
            busy      <= 1'b0;
            have_last <= 1'b0;
            scratch[0] <= 32'd0;
            scratch[1] <= 32'd0;
            scratch[2] <= 32'd0;
            cmds      <= 32'd0;
            refused   <= 32'd0;
            c_bad     <= 16'd0;
            c_short   <= 16'd0;
            c_long    <= 16'd0;
            c_rep     <= 16'd0;
            c_ooo     <= 16'd0;
            c_err     <= 16'd0;
            rlen      <= 5'd0;
            rplen     <= 5'd0;
            k         <= 5'd0;
            t         <= 2'd0;
            ridx      <= 7'd0;
            tidx      <= 7'd0;
            pend      <= 8'd0;
        end else begin
            // window registers
            if (win_wr) begin
                case (win_addr)
                    7'd1:    pend <= win_wdata[7:0];
                    7'd3:    ridx <= win_wdata[6:0];
                    7'd6:    tidx <= win_wdata[6:0];
                    default: ;
                endcase
            end
            if (pend != 8'd0 && !(win_wr && win_addr == 7'd1)) pend <= pend - 8'd1;

            case (state)
                S_RX: begin
                    if (in_wr) begin
                        busy <= 1'b1;
                        if (n != 8'hFF) n <= n + 8'd1;
                        if (win_wdata[8]) state <= S_EVAL;
                    end
                end
                S_EVAL: begin
                    n <= 8'd0;
                    if (r_bad)   c_bad   <= c_bad + 16'd1;
                    if (r_short) c_short <= c_short + 16'd1;
                    if (r_long)  c_long  <= c_long + 16'd1;
                    if (r_rep)   c_rep   <= c_rep + 16'd1;
                    if (r_ooo)   c_ooo   <= c_ooo + 16'd1;
                    if (r_err)   c_err   <= c_err + 16'd1;
                    if (d_stat_cnt) refused <= refused + 32'd1;
                    if (d_cmd)      cmds    <= cmds + 32'd1;
                    if (d_seqtake)  have_last <= 1'b1;
                    if (d_wr) begin
                        scratch[reg_no[1:0] - 2'd1] <= {pbuf[2], pbuf[3], pbuf[4], pbuf[5]};
                    end
                    if (d_reply) begin
                        rlen  <= 5'd9 + d_plen;
                        rplen <= d_plen;
                        k     <= 5'd0;
                        state <= S_PASS;
                    end else begin
                        rlen  <= 5'd0;
                        busy  <= 1'b0;
                        state <= S_RX;
                    end
                end
                S_PASS: begin
                    if (k == rplen + 5'd4) begin
                        state <= S_TRL;
                        t     <= 2'd0;
                    end else begin
                        k <= k + 5'd1;
                    end
                end
                default: begin   // S_TRL
                    t <= t + 2'd1;
                    if (t == 2'd3) begin
                        state <= S_RX;
                        busy  <= 1'b0;
                    end
                end
            endcase
        end
    end

    // ------------------------------------------------------------------ data registers (no reset)
    always_ff @(posedge clk) begin
        if (state == S_RX && in_wr) begin
            case (n)
                8'd0:    b_type <= win_wdata[7:0];
                8'd1:    b_len  <= win_wdata[7:0];
                8'd2:    b_seq[15:8] <= win_wdata[7:0];
                8'd3:    b_seq[7:0]  <= win_wdata[7:0];
                default: ;
            endcase
            if (n >= 8'd4 && n <= 8'd11) pbuf[n[2:0] + 3'd4] <= win_wdata[7:0];
        end
        if (state == S_EVAL) begin
            if (d_seqtake) last_seq <= b_seq;
            rbuf[0] <= b_type | 8'h80;
            rbuf[1] <= {5'd0, d_status};
            rbuf[2] <= b_seq[15:8];
            rbuf[3] <= b_seq[7:0];
            rbuf[4] <= {3'd0, d_plen};
            for (int i = 0; i < 17; i++) rbuf[5 + i] <= pay_vec[8 * (16 - i) +: 8];
        end
        if (state == S_TRL) begin
            rbuf[rplen + 5'd5 + {3'd0, t}] <= ~crc[8 * t +: 8];
        end
    end

    // ------------------------------------------------------------------ crc engine (shared by check and reply)
    assign crc_init = rst || (state == S_EVAL) || (state == S_TRL && t == 2'd3);
    assign crc_en   = (state == S_PASS) || (state == S_RX && in_wr);
    assign crc_data = (state == S_PASS) ? rbuf[k] : win_wdata[7:0];

    crc32_engine u_crc (.clk(clk), .init(crc_init), .en(crc_en), .data(crc_data), .crc(crc));

    // ------------------------------------------------------------------ telemetry
    assign tel_take = win_wr && (win_addr == 7'd8);

    telemetry #(.DEFAULT_PERIOD(DEFAULT_PERIOD), .MIN_PERIOD(MIN_PERIOD)) u_tel (
        .clk(clk), .rst(rst), .tick(tick),
        .start(tel_start), .start_period(reg_no), .stop(tel_stop), .take(tel_take),
        .cmds(cmds[15:0]), .refused(refused[15:0]), .tidx(tidx),
        .tel_on(tel_on), .period(period), .ticks(ticks), .fcount(fcount),
        .tlen(tlen), .tword(tword));

    // ------------------------------------------------------------------ window read
    logic [31:0] rword;
    always_comb begin
        logic [8:0] j;
        rword = 32'd0;
        for (int i = 0; i < 4; i++) begin
            j = {ridx, 2'b00} + 9'(i);
            if (j < {4'd0, rlen}) rword[31 - 8 * i -: 8] = rbuf[j[4:0]];
        end
    end

    always_ff @(posedge clk) begin
        if (win_rd) begin
            case (win_addr)
                7'd2:    win_rdata <= {27'd0, rlen};
                7'd3:    win_rdata <= {25'd0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= {27'd0, tlen};
                7'd6:    win_rdata <= {25'd0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'd0, busy, tel_on};
                default: win_rdata <= 32'd0;
            endcase
        end
    end
endmodule
