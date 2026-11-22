// uep_core: UDP command and telemetry endpoint logic behind the shell window.
//
// Packet bytes arrive through window register IN (bit 8 = last byte). A streaming
// CRC-32 runs over every byte including the trailer; a good packet leaves the
// register at the CRC-32 residue. After the last byte a short state machine
// classifies the packet (FIN1), applies the refusal order, counters and actions
// (FIN2), then builds the reply CRC one byte per clock (RCRC, RTRL): about 35
// clocks in all, inside the 100 clock limit. Telemetry frames are captured at the
// due tick and their CRC is built the same way by a second small machine.
module uep_core #(
    parameter logic [31:0] ID_WORD      = 32'h55445031,
    parameter int          PERIOD_RESET = 100,
    parameter int          PERIOD_MIN   = 4
) (
    input  logic        clk,
    input  logic        rst,          // synchronous, active high
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,    // bits 31:9 are not used by any register
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    localparam logic [31:0] CRC_INIT    = 32'hFFFF_FFFF;
    localparam logic [31:0] CRC_RESIDUE = 32'hDEBB_20E3;

    localparam logic [2:0] ST_IDLE = 3'd0, ST_FIN1 = 3'd1, ST_FIN2 = 3'd2, ST_RCRC = 3'd3, ST_RTRL = 3'd4;
    localparam logic [1:0] CLS_OK = 2'd0, CLS_SHORT = 2'd1, CLS_LONG = 2'd2, CLS_BAD = 2'd3;
    localparam logic [1:0] T_IDLE = 2'd0, T_CRC = 2'd1, T_TRL = 2'd2;

    function automatic logic [31:0] crc8(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] x;
        x = c ^ {24'b0, d};
        for (int i = 0; i < 8; i++) x = x[0] ? ((x >> 1) ^ 32'hEDB8_8320) : (x >> 1);
        return x;
    endfunction

    // ------------------------------------------------------------ window decode
    wire in_wr   = win_wr && (win_addr == 7'd0);
    wire tick_wr = win_wr && (win_addr == 7'd1);
    wire ridx_wr = win_wr && (win_addr == 7'd3);
    wire tidx_wr = win_wr && (win_addr == 7'd6);
    wire take_wr = win_wr && (win_addr == 7'd8);
    wire lastf   = win_wdata[8];

    // ------------------------------------------------------------ state
    logic [2:0]  st;
    logic [1:0]  tst;
    logic        rx_busy;
    logic [7:0]  pend;
    logic [31:0] ticks;
    logic        on, held;
    logic [15:0] pcount, period;
    logic [15:0] tseq, tfc;
    logic [15:0] cnt [0:6];
    logic [15:0] refused;
    logic [15:0] last_seq;
    logic        have_last;
    logic [31:0] regs [1:3];
    logic [6:0]  ridx, tidx;
    logic [4:0]  rlen;

    // receive datapath (no reset)
    logic [7:0]  pbuf [0:11];
    logic [4:0]  n;
    logic [31:0] rcrc;
    logic [1:0]  cls;
    logic        tk, lm, rbad;
    logic [1:0]  sq;
    logic [2:0]  rnum;
    logic [15:0] seq16, per16;

    // reply datapath (no reset)
    logic [7:0]  rbuf [0:31];
    logic [31:0] crc2;
    logic [4:0]  ri, rl;
    logic [1:0]  rk;

    // telemetry datapath (no reset)
    logic [7:0]  tbuf [0:31];
    logic [31:0] tcrc;
    logic [4:0]  ti;
    logic [1:0]  tkx;

    // ------------------------------------------------------------ packet decision
    logic [2:0] status;
    logic       do_ref, accept, seq_ok, noreply;
    logic [2:0] cidx;
    logic [4:0] plen;
    wire  [7:0] typ = pbuf[0];

    always_comb begin
        status  = 3'd0;
        do_ref  = 1'b0;
        accept  = 1'b0;
        seq_ok  = 1'b0;
        noreply = 1'b0;
        cidx    = 3'd0;
        if (cls != CLS_OK) begin
            noreply = 1'b1;
            do_ref  = 1'b1;
            case (cls)
                CLS_SHORT: cidx = 3'd2;
                CLS_LONG:  cidx = 3'd3;
                default:   cidx = 3'd1;
            endcase
        end else if (!tk) begin
            status = 3'd1; do_ref = 1'b1; cidx = 3'd6;
        end else if (!lm) begin
            status = 3'd2; do_ref = 1'b1; cidx = 3'd6;
        end else if (sq == 2'd1) begin
            status = 3'd4; do_ref = 1'b1; cidx = 3'd4;
        end else if (sq == 2'd2) begin
            status = 3'd4; do_ref = 1'b1; cidx = 3'd5;
        end else begin
            seq_ok = 1'b1;
            if ((typ == 8'd1 || typ == 8'd2) && rbad) begin
                status = 3'd3; do_ref = 1'b1; cidx = 3'd6;
            end else if (typ == 8'd2 && (rnum == 3'd0 || rnum >= 3'd4)) begin
                status = 3'd5; do_ref = 1'b1; cidx = 3'd6;
            end else begin
                accept = 1'b1;
            end
        end
    end

    always_comb begin
        plen = 5'd0;
        if (accept && typ == 8'd1) plen = 5'd4;
        if (accept && typ == 8'd3) plen = 5'd17;
    end

    logic [31:0] rval;
    always_comb begin
        case (rnum)
            3'd0:    rval = ID_WORD;
            3'd1:    rval = regs[1];
            3'd2:    rval = regs[2];
            3'd3:    rval = regs[3];
            3'd4:    rval = {16'b0, cnt[0]};
            3'd5:    rval = {16'b0, refused};
            3'd6:    rval = {16'b0, period};
            default: rval = ticks;
        endcase
    end

    wire [31:0] fin2 = ~crc2;
    wire [31:0] tfin = ~tcrc;

    // ------------------------------------------------------------ ticks and telemetry due
    wire        tick     = (pend != 8'd0);
    wire [9:0]  pend_sum = {2'b0, pend} - {9'b0, tick} + {2'b0, win_wdata[7:0]};
    wire [16:0] pcount_n = {1'b0, pcount} + 17'd1;
    wire        due      = tick && on && (pcount_n >= {1'b0, period});
    wire        cap      = due && !held;
    wire [31:0] ticks_n  = ticks + 32'd1;

    // ------------------------------------------------------------ control registers
    always_ff @(posedge clk) begin
        if (rst) begin
            st        <= ST_IDLE;
            tst       <= T_IDLE;
            rx_busy   <= 1'b0;
            pend      <= 8'd0;
            ticks     <= 32'd0;
            on        <= 1'b0;
            held      <= 1'b0;
            pcount    <= 16'd0;
            period    <= 16'(PERIOD_RESET);
            tseq      <= 16'd0;
            tfc       <= 16'd0;
            for (int i = 0; i < 7; i++) cnt[i] <= 16'd0;
            refused   <= 16'd0;
            last_seq  <= 16'd0;
            have_last <= 1'b0;
            for (int i = 1; i < 4; i++) regs[i] <= 32'd0;
            ridx      <= 7'd0;
            tidx      <= 7'd0;
            rlen      <= 5'd0;
        end else begin
            // window writes
            if (ridx_wr) ridx <= win_wdata[6:0];
            if (tidx_wr) tidx <= win_wdata[6:0];

            // pending ticks: add, saturate at 255, one tick per clock
            if (tick_wr)   pend <= (pend_sum > 10'd255) ? 8'd255 : pend_sum[7:0];
            else if (tick) pend <= pend - 8'd1;

            // ticks and telemetry period
            if (tick) begin
                ticks <= ticks_n;
                if (on) pcount <= due ? 16'd0 : pcount_n[15:0];
            end
            if (cap) begin
                held <= 1'b1;
                tst  <= T_CRC;
                tseq <= tseq + 16'd1;
                tfc  <= tfc + 16'd1;
            end
            if (tst == T_CRC && ti == 5'd12) tst <= T_TRL;
            if (tst == T_TRL && tkx == 2'd3) tst <= T_IDLE;

            // packet receive
            if (in_wr) begin
                rx_busy <= !lastf;
                if (lastf) st <= ST_FIN1;
            end

            case (st)
                ST_FIN1: begin
                    rlen <= 5'd0;
                    st   <= ST_FIN2;
                end
                ST_FIN2: begin
                    st <= noreply ? ST_IDLE : ST_RCRC;
                    if (do_ref) begin
                        cnt[cidx] <= cnt[cidx] + 16'd1;
                        refused   <= refused + 16'd1;
                    end
                    if (seq_ok) begin
                        last_seq  <= seq16;
                        have_last <= 1'b1;
                    end
                    if (accept) begin
                        cnt[0] <= cnt[0] + 16'd1;
                        case (typ)
                            8'd2: regs[rnum[1:0]] <= {pbuf[5], pbuf[6], pbuf[7], pbuf[8]};
                            8'd4: begin
                                on     <= 1'b1;
                                pcount <= 16'd0;
                                if (per16 != 16'd0)
                                    period <= (per16 < 16'(PERIOD_MIN)) ? 16'(PERIOD_MIN) : per16;
                            end
                            8'd5: begin
                                on   <= 1'b0;
                                held <= 1'b0;
                                tst  <= T_IDLE;
                            end
                            default: ;
                        endcase
                    end
                end
                ST_RCRC: if (ri == rl - 5'd1) st <= ST_RTRL;
                ST_RTRL: if (rk == 2'd3) begin
                    rlen <= rl + 5'd4;
                    st   <= ST_IDLE;
                end
                default: ;
            endcase

            // take register: releases the held frame
            if (take_wr) begin
                held <= 1'b0;
                tst  <= T_IDLE;
            end
        end
    end

    // ------------------------------------------------------------ receive datapath
    wire [4:0]  n_in   = rx_busy ? n : 5'd0;
    wire [31:0] crc_in = rx_busy ? rcrc : CRC_INIT;
    wire [8:0]  n9     = {4'b0, n};
    wire [8:0]  ln9    = {1'b0, pbuf[1]};
    wire [15:0] dseq   = {pbuf[2], pbuf[3]} - last_seq;

    always_ff @(posedge clk) begin
        if (in_wr) begin
            rcrc <= crc8(crc_in, win_wdata[7:0]);
            n    <= (n_in == 5'd31) ? 5'd31 : n_in + 5'd1;
            if (n_in < 5'd12) pbuf[n_in[3:0]] <= win_wdata[7:0];
        end
        if (st == ST_FIN1) begin
            if (n < 5'd4)                               cls <= CLS_SHORT;
            else if (pbuf[1] > 8'd8 || n9 > 9'd8 + ln9) cls <= CLS_LONG;
            else if (n9 < 9'd8 + ln9)                   cls <= CLS_SHORT;
            else if (rcrc != CRC_RESIDUE)               cls <= CLS_BAD;
            else                                        cls <= CLS_OK;
            case (pbuf[0])
                8'd1:    begin tk <= 1'b1; lm <= (pbuf[1] == 8'd2); end
                8'd2:    begin tk <= 1'b1; lm <= (pbuf[1] == 8'd6); end
                8'd3:    begin tk <= 1'b1; lm <= (pbuf[1] == 8'd0); end
                8'd4:    begin tk <= 1'b1; lm <= (pbuf[1] == 8'd2); end
                8'd5:    begin tk <= 1'b1; lm <= (pbuf[1] == 8'd0); end
                default: begin tk <= 1'b0; lm <= 1'b0; end
            endcase
            if (!have_last)         sq <= 2'd0;
            else if (dseq == 16'd0) sq <= 2'd1;
            else if (dseq[15])      sq <= 2'd2;
            else                    sq <= 2'd0;
            rbad  <= (pbuf[4] > 8'd7);
            rnum  <= pbuf[4][2:0];
            seq16 <= {pbuf[2], pbuf[3]};
            per16 <= {pbuf[4], pbuf[5]};
        end
    end

    // ------------------------------------------------------------ reply datapath
    always_ff @(posedge clk) begin
        if (st == ST_FIN2) begin
            rbuf[0] <= typ | 8'h80;
            rbuf[1] <= {5'b0, status};
            rbuf[2] <= pbuf[2];
            rbuf[3] <= pbuf[3];
            rbuf[4] <= {3'b0, plen};
            if (typ == 8'd3) begin
                rbuf[5] <= cnt[0][15:8]; rbuf[6] <= cnt[0][7:0];
                rbuf[7] <= cnt[1][15:8]; rbuf[8] <= cnt[1][7:0];
            end else begin
                rbuf[5] <= rval[31:24]; rbuf[6] <= rval[23:16];
                rbuf[7] <= rval[15:8];  rbuf[8] <= rval[7:0];
            end
            rbuf[9]  <= cnt[2][15:8]; rbuf[10] <= cnt[2][7:0];
            rbuf[11] <= cnt[3][15:8]; rbuf[12] <= cnt[3][7:0];
            rbuf[13] <= cnt[4][15:8]; rbuf[14] <= cnt[4][7:0];
            rbuf[15] <= cnt[5][15:8]; rbuf[16] <= cnt[5][7:0];
            rbuf[17] <= cnt[6][15:8]; rbuf[18] <= cnt[6][7:0];
            rbuf[19] <= tfc[15:8];    rbuf[20] <= tfc[7:0];
            rbuf[21] <= {7'b0, on};
            rl   <= 5'd5 + plen;
            ri   <= 5'd0;
            crc2 <= CRC_INIT;
        end
        if (st == ST_RCRC) begin
            crc2 <= crc8(crc2, rbuf[ri]);
            ri   <= ri + 5'd1;
            rk   <= 2'd0;
        end
        if (st == ST_RTRL) begin
            rbuf[rl + {3'b0, rk}] <= fin2[{rk, 3'b000} +: 8];
            rk <= rk + 2'd1;
        end
    end

    // ------------------------------------------------------------ telemetry datapath
    always_ff @(posedge clk) begin
        if (cap) begin
            tbuf[0]  <= 8'hC0;
            tbuf[1]  <= 8'h00;
            tbuf[2]  <= tseq[15:8];
            tbuf[3]  <= tseq[7:0];
            tbuf[4]  <= 8'd8;
            tbuf[5]  <= ticks_n[31:24];
            tbuf[6]  <= ticks_n[23:16];
            tbuf[7]  <= ticks_n[15:8];
            tbuf[8]  <= ticks_n[7:0];
            tbuf[9]  <= cnt[0][15:8];
            tbuf[10] <= cnt[0][7:0];
            tbuf[11] <= refused[15:8];
            tbuf[12] <= refused[7:0];
            ti       <= 5'd0;
            tcrc     <= CRC_INIT;
            tkx      <= 2'd0;
        end
        if (tst == T_CRC) begin
            tcrc <= crc8(tcrc, tbuf[ti]);
            ti   <= ti + 5'd1;
            tkx  <= 2'd0;
        end
        if (tst == T_TRL) begin
            tbuf[5'd13 + {3'b0, tkx}] <= tfin[{tkx, 3'b000} +: 8];
            tkx <= tkx + 2'd1;
        end
    end

    // ------------------------------------------------------------ read-back
    logic [31:0] rword, tword;
    always_comb begin
        rword = 32'd0;
        tword = 32'd0;
        for (int k = 0; k < 4; k++) begin
            logic [8:0] j, jt;
            j  = {ridx, 2'b00} + 9'(k);
            jt = {tidx, 2'b00} + 9'(k);
            if (j < {4'b0, rlen})
                rword[31 - 8*k -: 8] = rbuf[j[4:0]];
            if (held && jt < 9'd17)
                tword[31 - 8*k -: 8] = tbuf[jt[4:0]];
        end
    end

    wire busy = rx_busy || (st != ST_IDLE);

    always_ff @(posedge clk) begin
        if (win_rd) begin
            case (win_addr)
                7'd2:    win_rdata <= {27'b0, rlen};
                7'd3:    win_rdata <= {25'b0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= held ? 32'd17 : 32'd0;
                7'd6:    win_rdata <= {25'b0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'b0, busy, on};
                default: win_rdata <= 32'd0;
            endcase
        end
    end

    assign led = cnt[0];
endmodule
