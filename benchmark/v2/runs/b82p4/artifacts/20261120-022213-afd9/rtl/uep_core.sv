// uep_core.sv: UDP command and telemetry endpoint core (window registers, packet
// receive, CRC-32, command execution, reply builder, telemetry). One clock, synchronous
// active-high reset. Buffers (packet, reply, telemetry frame) are not reset: their
// content is only read when the matching valid flag is set.
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
    input  logic [31:0] win_wdata,   // only bits [8:0] are used (IN register is 9 bits wide)
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    localparam logic [31:0] CRC_INIT    = 32'hFFFFFFFF;
    localparam logic [31:0] CRC_RESIDUE = 32'hDEBB20E3;

    typedef enum logic [2:0] {S_IDLE, S_DECIDE, S_CRC, S_EXEC, S_RCRC} state_t;
    state_t state;

    // ---- packet buffer and receive state
    logic [7:0]  pbuf [0:15];
    logic [4:0]  pn;
    logic        busy;
    logic [31:0] crc;
    logic [4:0]  ci;

    // ---- reply buffer
    logic [7:0]  rbuf [0:31];
    logic [4:0]  rbl;
    logic        rvalid;
    logic [31:0] rcrc;

    // ---- registers and counters
    logic [31:0] sc [0:2];
    logic [15:0] cnt [0:6];
    logic [31:0] refused;
    logic [15:0] last_seq;
    logic        have_last;
    logic [15:0] period;
    logic [31:0] ticks;

    // ---- telemetry
    logic        on;
    logic [15:0] tcount;
    logic [7:0]  pending;
    logic [15:0] fseq, fcount;
    logic [7:0]  tbuf [0:15];
    logic [3:0]  ti;
    logic        tbuild, held;
    logic [31:0] tcrc;

    logic [6:0]  ridx, tidx;

    function automatic logic [31:0] crc8(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] x;
        x = c ^ {24'h0, d};
        for (int k = 0; k < 8; k++) x = x[0] ? ((x >> 1) ^ 32'hEDB88320) : (x >> 1);
        return x;
    endfunction

    assign led = cnt[0];

    // ---- packet field decode
    wire [7:0]  p_typ  = pbuf[0];
    wire [7:0]  p_len  = pbuf[1];
    wire [15:0] p_seq  = {pbuf[2], pbuf[3]};
    wire [4:0]  n_need = 5'd8 + {1'b0, p_len[3:0]};
    wire        len_big = (p_len > 8'd8);

    logic [2:0]  req_len;
    logic        type_ok, len_ok;
    always_comb begin
        type_ok = 1'b1;
        case (p_typ)
            8'd1:    req_len = 3'd2;
            8'd2:    req_len = 3'd6;
            8'd3:    req_len = 3'd0;
            8'd4:    req_len = 3'd2;
            8'd5:    req_len = 3'd0;
            default: begin req_len = 3'd0; type_ok = 1'b0; end
        endcase
        len_ok = (p_len == {5'b0, req_len});
    end

    wire [15:0] seq_d   = p_seq - last_seq;
    wire        seq_rep = have_last && (seq_d == 16'd0);
    wire        seq_ok  = !have_last || ((seq_d != 16'd0) && !seq_d[15]);
    // register number: read uses the 2-byte field (high byte first); write uses the first payload byte
    wire [7:0]  d_reg   = (p_typ == 8'd2) ? pbuf[4] : ((pbuf[4] == 8'd0) ? pbuf[5] : 8'hFF);

    logic [2:0] d_status;
    logic       d_refuse, d_use_seq;
    logic [2:0] d_ridx;
    always_comb begin
        d_status  = 3'd0;
        d_refuse  = 1'b0;
        d_use_seq = 1'b0;
        d_ridx    = 3'd6;
        if (!type_ok) begin
            d_status = 3'd1; d_refuse = 1'b1;
        end else if (!len_ok) begin
            d_status = 3'd2; d_refuse = 1'b1;
        end else if (!seq_ok) begin
            d_status = 3'd4; d_refuse = 1'b1;
            d_ridx   = seq_rep ? 3'd4 : 3'd5;
        end else begin
            d_use_seq = 1'b1;
            if (p_typ == 8'd1 || p_typ == 8'd2) begin
                if (d_reg[7:3] != 5'd0) begin
                    d_status = 3'd3; d_refuse = 1'b1;
                end else if (p_typ == 8'd2 && (d_reg[2:0] == 3'd0 || d_reg[2] == 1'b1)) begin
                    d_status = 3'd5; d_refuse = 1'b1;
                end
            end
        end
    end

    logic [31:0] rd_val;
    always_comb begin
        case (d_reg[2:0])
            3'd0:    rd_val = ID_WORD;
            3'd1:    rd_val = sc[0];
            3'd2:    rd_val = sc[1];
            3'd3:    rd_val = sc[2];
            3'd4:    rd_val = {16'h0, cnt[0]};
            3'd5:    rd_val = refused;
            3'd6:    rd_val = {16'h0, period};
            default: rd_val = ticks;
        endcase
    end

    // ---- counter increments (one per finished packet)
    logic       inc_en, refuse_en;
    logic [2:0] inc_idx;
    wire        dec_short = (pn < 5'd4) || (!len_big && pn < n_need);
    wire        dec_long  = !dec_short && (len_big || pn > n_need);
    wire        crc_done  = (ci == pn);
    wire        crc_bad   = (crc != CRC_RESIDUE);
    always_comb begin
        inc_en    = 1'b0;
        refuse_en = 1'b0;
        inc_idx   = 3'd0;
        case (state)
            S_DECIDE: begin
                if (dec_short) begin inc_en = 1'b1; refuse_en = 1'b1; inc_idx = 3'd2; end
                else if (dec_long) begin inc_en = 1'b1; refuse_en = 1'b1; inc_idx = 3'd3; end
            end
            S_CRC: begin
                if (crc_done && crc_bad) begin inc_en = 1'b1; refuse_en = 1'b1; inc_idx = 3'd1; end
            end
            S_EXEC: begin
                inc_en    = 1'b1;
                refuse_en = d_refuse;
                inc_idx   = d_refuse ? d_ridx : 3'd0;
            end
            default: ;
        endcase
    end

    // ---- tick / telemetry
    wire [31:0] ticks_n = ticks + 32'd1;
    wire [15:0] tc_n    = tcount + 16'd1;

    // ---- host read words
    logic [31:0] rword, tword;
    logic [8:0]  jj, js;
    logic [7:0]  bb;
    always_comb begin
        rword = 32'h0;
        tword = 32'h0;
        jj = 9'h0; js = 9'h0; bb = 8'h0;
        for (int k = 0; k < 4; k++) begin
            jj = {ridx, 2'b00} + 9'(k);
            bb = 8'h00;
            js = jj - {4'b0, rbl};
            if (rvalid) begin
                if (jj < {4'b0, rbl}) bb = rbuf[jj[4:0]];
                else if (js < 9'd4)   bb = rcrc[{js[1:0], 3'b000} +: 8];
            end
            rword[8*(3-k) +: 8] = bb;
        end
        for (int k = 0; k < 4; k++) begin
            jj = {tidx, 2'b00} + 9'(k);
            bb = 8'h00;
            js = jj - 9'd13;
            if (held) begin
                if (jj < 9'd13)      bb = tbuf[jj[3:0]];
                else if (js < 9'd4)  bb = tcrc[{js[1:0], 3'b000} +: 8];
            end
            tword[8*(3-k) +: 8] = bb;
        end
    end

    logic [31:0] rmux;
    always_comb begin
        case (win_addr)
            7'd2:    rmux = rvalid ? {27'h0, rbl} + 32'd4 : 32'h0;
            7'd3:    rmux = {25'h0, ridx};
            7'd4:    rmux = rword;
            7'd5:    rmux = held ? 32'd17 : 32'd0;
            7'd6:    rmux = {25'h0, tidx};
            7'd7:    rmux = tword;
            7'd9:    rmux = {30'h0, busy, on};
            default: rmux = 32'h0;
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            state     <= S_IDLE;
            pn        <= '0;
            busy      <= 1'b0;
            ci        <= '0;
            rbl       <= '0;
            rvalid    <= 1'b0;
            refused   <= '0;
            last_seq  <= '0;
            have_last <= 1'b0;
            period    <= 16'(PERIOD_RESET);
            ticks     <= '0;
            on        <= 1'b0;
            tcount    <= '0;
            pending   <= '0;
            fseq      <= '0;
            fcount    <= '0;
            ti        <= '0;
            tbuild    <= 1'b0;
            held      <= 1'b0;
            ridx      <= '0;
            tidx      <= '0;
            crc       <= CRC_INIT;
            rcrc      <= '0;
            tcrc      <= '0;
            win_rdata <= '0;
            for (int i = 0; i < 3; i++) sc[i]  <= '0;
            for (int i = 0; i < 7; i++) cnt[i] <= '0;
        end else begin
            // host read data, valid the cycle after win_rd
            if (win_rd) win_rdata <= rmux;

            // telemetry frame builder
            if (tbuild) begin
                if (ti < 4'd13) begin
                    tcrc <= crc8(tcrc, tbuf[ti]);
                    ti   <= ti + 4'd1;
                end else begin
                    tcrc   <= ~tcrc;
                    held   <= 1'b1;
                    tbuild <= 1'b0;
                end
            end

            // ticks
            if (pending != 8'd0) begin
                pending <= pending - 8'd1;
                ticks   <= ticks_n;
                if (on) begin
                    if (tc_n >= period) begin
                        tcount <= 16'd0;
                        if (!held && !tbuild) begin
                            tbuf[0]  <= 8'hC0;
                            tbuf[1]  <= 8'h00;
                            tbuf[2]  <= fseq[15:8];
                            tbuf[3]  <= fseq[7:0];
                            tbuf[4]  <= 8'd8;
                            tbuf[5]  <= ticks_n[31:24];
                            tbuf[6]  <= ticks_n[23:16];
                            tbuf[7]  <= ticks_n[15:8];
                            tbuf[8]  <= ticks_n[7:0];
                            tbuf[9]  <= cnt[0][15:8];
                            tbuf[10] <= cnt[0][7:0];
                            tbuf[11] <= refused[15:8];
                            tbuf[12] <= refused[7:0];
                            fseq     <= fseq + 16'd1;
                            fcount   <= fcount + 16'd1;
                            tbuild   <= 1'b1;
                            ti       <= 4'd0;
                            tcrc     <= CRC_INIT;
                        end
                    end else begin
                        tcount <= tc_n;
                    end
                end
            end

            // host window writes
            if (win_wr) begin
                case (win_addr)
                    7'd0: begin
                        if (state == S_IDLE) begin
                            if (pn < 5'd16) pbuf[pn[3:0]] <= win_wdata[7:0];
                            if (pn != 5'd31) pn <= pn + 5'd1;
                            busy <= 1'b1;
                            if (win_wdata[8]) begin
                                rvalid <= 1'b0;
                                state  <= S_DECIDE;
                            end
                        end
                    end
                    7'd1: pending <= win_wdata[7:0];
                    7'd3: ridx    <= win_wdata[6:0];
                    7'd6: tidx    <= win_wdata[6:0];
                    7'd8: begin
                        held   <= 1'b0;
                        tbuild <= 1'b0;
                    end
                    default: ;
                endcase
            end

            // counters
            if (inc_en) cnt[inc_idx] <= cnt[inc_idx] + 16'd1;
            if (refuse_en) refused <= refused + 32'd1;

            // packet state machine
            case (state)
                S_DECIDE: begin
                    if (dec_short || dec_long) begin
                        state <= S_IDLE;
                        busy  <= 1'b0;
                        pn    <= '0;
                    end else begin
                        crc   <= CRC_INIT;
                        ci    <= '0;
                        state <= S_CRC;
                    end
                end
                S_CRC: begin
                    if (!crc_done) begin
                        crc <= crc8(crc, pbuf[ci[3:0]]);
                        ci  <= ci + 5'd1;
                    end else if (crc_bad) begin
                        state <= S_IDLE;
                        busy  <= 1'b0;
                        pn    <= '0;
                    end else begin
                        state <= S_EXEC;
                    end
                end
                S_EXEC: begin
                    rbuf[0] <= p_typ | 8'h80;
                    rbuf[1] <= {5'b0, d_status};
                    rbuf[2] <= pbuf[2];
                    rbuf[3] <= pbuf[3];
                    rbuf[4] <= 8'd0;
                    rbl     <= 5'd5;
                    if (d_use_seq) begin
                        last_seq  <= p_seq;
                        have_last <= 1'b1;
                    end
                    if (!d_refuse) begin
                        case (p_typ)
                            8'd1: begin
                                rbuf[4] <= 8'd4;
                                rbl     <= 5'd9;
                                rbuf[5] <= rd_val[31:24];
                                rbuf[6] <= rd_val[23:16];
                                rbuf[7] <= rd_val[15:8];
                                rbuf[8] <= rd_val[7:0];
                            end
                            8'd2: begin
                                case (d_reg[1:0])
                                    2'd1: sc[0] <= {pbuf[5], pbuf[6], pbuf[7], pbuf[8]};
                                    2'd2: sc[1] <= {pbuf[5], pbuf[6], pbuf[7], pbuf[8]};
                                    default: sc[2] <= {pbuf[5], pbuf[6], pbuf[7], pbuf[8]};
                                endcase
                            end
                            8'd3: begin
                                rbuf[4] <= 8'd17;
                                rbl     <= 5'd22;
                                for (int i = 0; i < 7; i++) begin
                                    rbuf[5 + 2*i] <= cnt[i][15:8];
                                    rbuf[6 + 2*i] <= cnt[i][7:0];
                                end
                                rbuf[19] <= fcount[15:8];
                                rbuf[20] <= fcount[7:0];
                                rbuf[21] <= {7'b0, on};
                            end
                            8'd4: begin
                                if ({pbuf[4], pbuf[5]} != 16'd0)
                                    period <= ({pbuf[4], pbuf[5]} < 16'(PERIOD_MIN)) ? 16'(PERIOD_MIN)
                                                                                    : {pbuf[4], pbuf[5]};
                                on     <= 1'b1;
                                tcount <= 16'd0;
                            end
                            default: begin   // 5: stop
                                on     <= 1'b0;
                                held   <= 1'b0;
                                tbuild <= 1'b0;
                            end
                        endcase
                    end
                    pn    <= '0;
                    crc   <= CRC_INIT;
                    ci    <= '0;
                    state <= S_RCRC;
                end
                S_RCRC: begin
                    if (ci < rbl) begin
                        crc <= crc8(crc, rbuf[ci]);
                        ci  <= ci + 5'd1;
                    end else begin
                        rcrc   <= ~crc;
                        rvalid <= 1'b1;
                        busy   <= 1'b0;
                        state  <= S_IDLE;
                    end
                end
                default: ;
            endcase
        end
    end
endmodule
