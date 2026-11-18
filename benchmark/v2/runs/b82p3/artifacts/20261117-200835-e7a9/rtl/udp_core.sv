// udp_core: UDP-style command and telemetry endpoint behind the test-shell register window.
// One clock domain, synchronous active-high reset. Behaviour follows spec.yaml (and model.py).
module udp_core #(
    parameter logic [31:0] ID_WORD       = 32'h55445031,
    parameter logic [15:0] PERIOD_RESET  = 16'd100,
    parameter logic [15:0] PERIOD_MIN    = 16'd4
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,   // only bits 8:0 are used by the IN register
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    localparam logic [31:0] CRC_INIT    = 32'hFFFF_FFFF;
    localparam logic [31:0] CRC_RESIDUE = 32'hDEBB_20E3;

    function automatic logic [31:0] crc8(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] r;
        r = c ^ {24'b0, d};
        for (int i = 0; i < 8; i++) r = r[0] ? ((r >> 1) ^ 32'hEDB8_8320) : (r >> 1);
        return r;
    endfunction

    // ------------------------------------------------------------------ state
    typedef enum logic [1:0] {P_IDLE, P_EVAL, P_CRC, P_TRL} pstate_t;
    pstate_t pstate;

    logic [7:0]  pbuf [12];
    logic [8:0]  pn;
    logic [31:0] pcrc;
    logic        busy;
    logic [7:0]  rbuf [32];
    logic [4:0]  rlen;
    logic [4:0]  rplen;
    logic [4:0]  rk;
    logic [6:0]  ridx, tidx;

    logic        have_last;
    logic [15:0] last_seq;
    logic [31:0] scratch1, scratch2, scratch3;
    logic [31:0] cnt_ok, cnt_ref;
    logic [15:0] c_bad, c_short, c_long, c_rep, c_ooo, c_oth;

    logic [15:0] period, tcnt, fcnt;
    logic        tele_on;
    logic [7:0]  pending;
    logic [31:0] ticks;
    logic        held;
    logic [1:0]  hph;          // 0 idle, 1 crc, 2 trailer
    logic [7:0]  hbuf [17];
    logic [31:0] hcrc;
    logic [4:0]  hk;

    // ------------------------------------------------------------ evaluation
    wire [7:0]  e_typ = pbuf[0];
    wire [7:0]  e_ln  = pbuf[1];
    wire [15:0] e_seq = {pbuf[2], pbuf[3]};
    wire [15:0] e_reg = {pbuf[4], pbuf[5]};
    wire [8:0]  need_n = 9'd8 + {1'b0, e_ln};
    wire [15:0] seq_d  = e_seq - last_seq;

    logic        drop, seq_pass;
    logic [2:0]  cat;
    logic [7:0]  status;
    logic [7:0]  need_ln;
    logic [31:0] regval;

    always_comb begin
        case (e_typ)
            8'd1:    need_ln = 8'd2;
            8'd2:    need_ln = 8'd6;
            8'd3:    need_ln = 8'd0;
            8'd4:    need_ln = 8'd2;
            default: need_ln = 8'd0;   // type 5 (unknown types are caught first)
        endcase
        case (e_reg[2:0])
            3'd0:    regval = ID_WORD;
            3'd1:    regval = scratch1;
            3'd2:    regval = scratch2;
            3'd3:    regval = scratch3;
            3'd4:    regval = cnt_ok;
            3'd5:    regval = cnt_ref;
            3'd6:    regval = {16'b0, period};
            default: regval = ticks;
        endcase
        drop = 1'b0; cat = 3'd0; status = 8'd0; seq_pass = 1'b0;
        if (pn < 9'd4) begin
            drop = 1'b1; cat = 3'd2;
        end else if (e_ln > 8'd8 || pn > need_n) begin
            drop = 1'b1; cat = 3'd3;
        end else if (pn < need_n) begin
            drop = 1'b1; cat = 3'd2;
        end else if (pcrc != CRC_RESIDUE) begin
            drop = 1'b1; cat = 3'd1;
        end else if (e_typ == 8'd0 || e_typ > 8'd5) begin
            cat = 3'd6; status = 8'd1;
        end else if (e_ln != need_ln) begin
            cat = 3'd6; status = 8'd2;
        end else if (have_last && (seq_d == 16'd0 || seq_d[15])) begin
            cat = (seq_d == 16'd0) ? 3'd4 : 3'd5; status = 8'd4;
        end else begin
            seq_pass = 1'b1;
            if (e_typ == 8'd1 || e_typ == 8'd2) begin
                if (e_reg[15:3] != 13'd0) begin
                    cat = 3'd6; status = 8'd3;
                end else if (e_typ == 8'd2 && (e_reg[2:0] == 3'd0 || e_reg[2])) begin
                    cat = 3'd6; status = 8'd5;
                end
            end
        end
    end

    // ---------------------------------------------------------- tick / telemetry events
    wire        tick     = (pending != 8'd0);
    wire [16:0] tnext    = {1'b0, tcnt} + 17'd1;
    wire        due      = tick && tele_on && (tnext >= {1'b0, period});
    wire        take_now = win_wr && (win_addr == 7'd8);
    wire [31:0] ticks_n  = ticks + 32'd1;
    wire [5:0]  rmsg_len = 6'd5 + {1'b0, rplen};

    // ------------------------------------------------------------------ main
    always_ff @(posedge clk) begin
        if (rst) begin
            pstate    <= P_IDLE;
            pn        <= '0;
            pcrc      <= CRC_INIT;
            busy      <= 1'b0;
            rlen      <= '0;
            rplen     <= '0;
            rk        <= '0;
            ridx      <= '0;
            tidx      <= '0;
            have_last <= 1'b0;
            last_seq  <= '0;
            scratch1  <= '0;
            scratch2  <= '0;
            scratch3  <= '0;
            cnt_ok    <= '0;
            cnt_ref   <= '0;
            c_bad     <= '0;
            c_short   <= '0;
            c_long    <= '0;
            c_rep     <= '0;
            c_ooo     <= '0;
            c_oth     <= '0;
            period    <= PERIOD_RESET;
            tcnt      <= '0;
            fcnt      <= '0;
            tele_on   <= 1'b0;
            pending   <= '0;
            ticks     <= '0;
            held      <= 1'b0;
            hph       <= '0;
        end else begin
            // ---- register window writes
            if (win_wr) begin
                case (win_addr)
                    7'd1: pending <= win_wdata[7:0];
                    7'd3: ridx    <= win_wdata[6:0];
                    7'd6: tidx    <= win_wdata[6:0];
                    default: ;
                endcase
            end
            if (tick && !(win_wr && win_addr == 7'd1)) pending <= pending - 8'd1;
            if (tick) ticks <= ticks_n;

            // ---- packet byte intake
            if (win_wr && win_addr == 7'd0 && pstate == P_IDLE) begin
                if (pn < 9'd12) pbuf[pn[3:0]] <= win_wdata[7:0];
                pcrc <= crc8(pcrc, win_wdata[7:0]);
                if (pn != 9'd511) pn <= pn + 9'd1;
                if (win_wdata[8]) begin
                    pstate <= P_EVAL;
                    busy   <= 1'b1;
                    rlen   <= '0;
                end
            end

            // ---- telemetry period count and frame creation
            if (tick && tele_on) tcnt <= due ? 16'd0 : tnext[15:0];
            if (take_now) begin
                held <= 1'b0;
                hph  <= '0;
            end
            if (due && (!held || take_now)) begin
                held    <= 1'b1;
                hph     <= 2'd1;
                hk      <= '0;
                hcrc    <= CRC_INIT;
                fcnt    <= fcnt + 16'd1;
                hbuf[0]  <= 8'hC0;
                hbuf[1]  <= 8'h00;
                hbuf[2]  <= fcnt[15:8];
                hbuf[3]  <= fcnt[7:0];
                hbuf[4]  <= 8'd8;
                hbuf[5]  <= ticks_n[31:24];
                hbuf[6]  <= ticks_n[23:16];
                hbuf[7]  <= ticks_n[15:8];
                hbuf[8]  <= ticks_n[7:0];
                hbuf[9]  <= cnt_ok[15:8];
                hbuf[10] <= cnt_ok[7:0];
                hbuf[11] <= cnt_ref[15:8];
                hbuf[12] <= cnt_ref[7:0];
            end else if (hph == 2'd1) begin
                hcrc <= crc8(hcrc, hbuf[hk]);
                hk   <= hk + 5'd1;
                if (hk == 5'd12) hph <= 2'd2;
            end else if (hph == 2'd2) begin
                hbuf[13] <= ~hcrc[7:0];
                hbuf[14] <= ~hcrc[15:8];
                hbuf[15] <= ~hcrc[23:16];
                hbuf[16] <= ~hcrc[31:24];
                hph      <= 2'd0;
            end

            // ---- packet evaluation and reply build
            case (pstate)
                P_EVAL: begin
                    pn   <= '0;
                    pcrc <= CRC_INIT;
                    if (drop) begin
                        cnt_ref <= cnt_ref + 32'd1;
                        case (cat)
                            3'd1:    c_bad   <= c_bad + 16'd1;
                            3'd2:    c_short <= c_short + 16'd1;
                            default: c_long  <= c_long + 16'd1;
                        endcase
                        busy   <= 1'b0;
                        pstate <= P_IDLE;
                    end else begin
                        rbuf[0] <= e_typ | 8'h80;
                        rbuf[1] <= status;
                        rbuf[2] <= pbuf[2];
                        rbuf[3] <= pbuf[3];
                        rbuf[4] <= 8'd0;
                        rplen   <= 5'd0;
                        rk      <= '0;
                        pstate  <= P_CRC;
                        if (seq_pass) begin
                            have_last <= 1'b1;
                            last_seq  <= e_seq;
                        end
                        if (status != 8'd0) begin
                            cnt_ref <= cnt_ref + 32'd1;
                            case (cat)
                                3'd4:    c_rep <= c_rep + 16'd1;
                                3'd5:    c_ooo <= c_ooo + 16'd1;
                                default: c_oth <= c_oth + 16'd1;
                            endcase
                        end else begin
                            cnt_ok <= cnt_ok + 32'd1;
                            case (e_typ)
                                8'd1: begin
                                    rbuf[4] <= 8'd4;
                                    rplen   <= 5'd4;
                                    rbuf[5] <= regval[31:24];
                                    rbuf[6] <= regval[23:16];
                                    rbuf[7] <= regval[15:8];
                                    rbuf[8] <= regval[7:0];
                                end
                                8'd2: begin
                                    case (e_reg[1:0])
                                        2'd1:    scratch1 <= {pbuf[6], pbuf[7], pbuf[8], pbuf[9]};
                                        2'd2:    scratch2 <= {pbuf[6], pbuf[7], pbuf[8], pbuf[9]};
                                        default: scratch3 <= {pbuf[6], pbuf[7], pbuf[8], pbuf[9]};
                                    endcase
                                end
                                8'd3: begin
                                    rbuf[4]  <= 8'd17;
                                    rplen    <= 5'd17;
                                    rbuf[5]  <= cnt_ok[15:8];
                                    rbuf[6]  <= cnt_ok[7:0];
                                    rbuf[7]  <= c_bad[15:8];
                                    rbuf[8]  <= c_bad[7:0];
                                    rbuf[9]  <= c_short[15:8];
                                    rbuf[10] <= c_short[7:0];
                                    rbuf[11] <= c_long[15:8];
                                    rbuf[12] <= c_long[7:0];
                                    rbuf[13] <= c_rep[15:8];
                                    rbuf[14] <= c_rep[7:0];
                                    rbuf[15] <= c_ooo[15:8];
                                    rbuf[16] <= c_ooo[7:0];
                                    rbuf[17] <= c_oth[15:8];
                                    rbuf[18] <= c_oth[7:0];
                                    rbuf[19] <= fcnt[15:8];
                                    rbuf[20] <= fcnt[7:0];
                                    rbuf[21] <= {7'b0, tele_on};
                                end
                                8'd4: begin
                                    if (e_reg != 16'd0)
                                        period <= (e_reg < PERIOD_MIN) ? PERIOD_MIN : e_reg;
                                    tele_on <= 1'b1;
                                    tcnt    <= '0;
                                end
                                default: begin   // type 5: stop
                                    tele_on <= 1'b0;
                                    held    <= 1'b0;
                                    hph     <= '0;
                                end
                            endcase
                        end
                    end
                end
                P_CRC: begin
                    pcrc <= crc8(pcrc, rbuf[rk]);
                    rk   <= rk + 5'd1;
                    if ({1'b0, rk} == rmsg_len - 6'd1) pstate <= P_TRL;
                end
                P_TRL: begin
                    rbuf[rmsg_len[4:0]]         <= ~pcrc[7:0];
                    rbuf[rmsg_len[4:0] + 5'd1]  <= ~pcrc[15:8];
                    rbuf[rmsg_len[4:0] + 5'd2]  <= ~pcrc[23:16];
                    rbuf[rmsg_len[4:0] + 5'd3]  <= ~pcrc[31:24];
                    rlen   <= rplen + 5'd9;
                    pcrc   <= CRC_INIT;
                    busy   <= 1'b0;
                    pstate <= P_IDLE;
                end
                default: ;
            endcase
        end
    end

    // ------------------------------------------------------------ register reads
    logic [31:0] rword, tword, rd_next;
    always_comb begin
        logic [8:0] rj, tj;
        logic [8:0] jr, jt;
        rword = '0;
        tword = '0;
        rj = {ridx, 2'b00};
        tj = {tidx, 2'b00};
        for (int k = 0; k < 4; k++) begin
            jr = rj + 9'(k);
            jt = tj + 9'(k);
            if (jr < {4'b0, rlen})
                rword[31 - 8*k -: 8] = rbuf[jr[4:0]];
            if (held && jt < 9'd17)
                tword[31 - 8*k -: 8] = hbuf[jt[4:0]];
        end
        case (win_addr)
            7'd2:    rd_next = {27'b0, rlen};
            7'd3:    rd_next = {25'b0, ridx};
            7'd4:    rd_next = rword;
            7'd5:    rd_next = held ? 32'd17 : 32'd0;
            7'd6:    rd_next = {25'b0, tidx};
            7'd7:    rd_next = tword;
            7'd9:    rd_next = {30'b0, busy, tele_on};
            default: rd_next = 32'd0;
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else     win_rdata <= rd_next;
    end

    assign led = cnt_ok[15:0];
endmodule
