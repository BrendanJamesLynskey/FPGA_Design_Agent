// UDP command and telemetry endpoint core (payload level). One clock, synchronous active-high reset.
// Packet bytes arrive through window register IN; the packet is judged, CRC-checked (byte-serial),
// executed, and the reply is built in a register buffer with a byte-serial CRC-32.
module udp_endpoint_core #(
    parameter logic [31:0] ID_WORD              = 32'h55445031,
    parameter int          DEFAULT_PERIOD_TICKS = 100,
    parameter int          MIN_PERIOD_TICKS     = 4,
    parameter int          READ_LEN             = 2,   // spec: read length byte 2
    parameter int          WRITE_LEN            = 6    // spec: write length byte 6
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
    localparam logic [31:0] CRC_INIT    = 32'hFFFFFFFF;
    localparam logic [31:0] CRC_RESIDUE = 32'hDEBB20E3;
    localparam logic [15:0] DEF_PERIOD  = 16'(DEFAULT_PERIOD_TICKS);
    localparam logic [15:0] MIN_PERIOD  = 16'(MIN_PERIOD_TICKS);
    localparam logic [7:0]  RD_LEN      = 8'(READ_LEN);
    localparam logic [7:0]  WR_LEN      = 8'(WRITE_LEN);

    function automatic logic [31:0] crc8(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] x;
        x = c ^ {24'b0, d};
        for (int i = 0; i < 8; i++) x = x[0] ? ((x >> 1) ^ 32'hEDB88320) : (x >> 1);
        return x;
    endfunction

    typedef enum logic [2:0] {S_IDLE, S_JUDGE, S_CRC, S_EXEC, S_RCRC} st_t;
    st_t st;

    // ---------------- storage
    logic [7:0]  pbuf [0:15];
    logic [7:0]  rbuf [0:31];
    logic [7:0]  tbuf [0:16];
    logic [4:0]  nb, plen;          // bytes received so far / packet length (saturating at 31)
    logic [31:0] crc;
    logic [4:0]  cidx, rm, rlen;
    logic [15:0] cnt [0:6];
    logic [31:0] refused;
    logic [15:0] last;
    logic        have_last;
    logic [31:0] scratch [0:2];
    logic [6:0]  ridx, tidx;
    // telemetry / time
    logic [7:0]  pend;
    logic [31:0] ticks;
    logic        tel_on, held, tbusy;
    logic [15:0] period, tcount, fcnt;
    logic [31:0] tcrc;
    logic [4:0]  tci;

    assign led = cnt[0];

    // ---------------- judge decisions (S_JUDGE)
    logic [7:0] typ, blen, p0;
    logic [15:0] seqn, dseq;
    assign typ  = pbuf[0];
    assign blen = pbuf[1];
    assign p0   = pbuf[4];
    assign seqn = {pbuf[2], pbuf[3]};
    assign dseq = seqn - last;

    logic [8:0] exp_n;
    logic       j_short1, j_long, j_short2;
    always_comb begin
        exp_n    = {1'b0, blen} + 9'd8;
        j_short1 = plen < 5'd4;
        j_long   = !j_short1 && ((blen > 8'd8) || ({4'b0, plen} > exp_n));
        j_short2 = !j_short1 && !j_long && ({4'b0, plen} < exp_n);
    end

    // ---------------- execute decisions (S_EXEC)
    logic [7:0] want;
    logic       type_ok, len_ok, seq_ok, reg_bad, ro_bad;
    logic [2:0] status;
    always_comb begin
        case (typ)
            8'd1:    want = RD_LEN;
            8'd2:    want = WR_LEN;
            8'd4:    want = 8'd2;
            default: want = 8'd0;
        endcase
        type_ok = (typ >= 8'd1) && (typ <= 8'd5);
        len_ok  = (blen == want);
        seq_ok  = !have_last || ((dseq != 16'd0) && !dseq[15]);
        reg_bad = ((typ == 8'd1) || (typ == 8'd2)) && (p0 >= 8'd8);
        ro_bad  = (typ == 8'd2) && ((p0 == 8'd0) || (p0 >= 8'd4));
        if (!type_ok)      status = 3'd1;
        else if (!len_ok)  status = 3'd2;
        else if (!seq_ok)  status = 3'd4;
        else if (reg_bad)  status = 3'd3;
        else if (ro_bad)   status = 3'd5;
        else               status = 3'd0;
    end

    logic ex_ok, ex_start, ex_stop;
    assign ex_ok    = (st == S_EXEC) && (status == 3'd0);
    assign ex_start = ex_ok && (typ == 8'd4);
    assign ex_stop  = ex_ok && (typ == 8'd5);

    logic [6:0] inc;
    always_comb begin
        inc = '0;
        case (st)
            S_JUDGE: begin
                if (j_short1 || j_short2) inc[2] = 1'b1;
                else if (j_long)          inc[3] = 1'b1;
            end
            S_CRC: if ((cidx == plen) && (crc != CRC_RESIDUE)) inc[1] = 1'b1;
            S_EXEC: begin
                if (status == 3'd0)      inc[0] = 1'b1;
                else if (status == 3'd4) begin
                    if (dseq == 16'd0) inc[4] = 1'b1;
                    else               inc[5] = 1'b1;
                end else                 inc[6] = 1'b1;
            end
            default: ;
        endcase
    end

    logic [31:0] rval;
    always_comb begin
        case (p0[2:0])
            3'd0:    rval = ID_WORD;
            3'd1:    rval = scratch[0];
            3'd2:    rval = scratch[1];
            3'd3:    rval = scratch[2];
            3'd4:    rval = {16'b0, cnt[0]};
            3'd5:    rval = refused;
            3'd6:    rval = {16'b0, period};
            default: rval = ticks;
        endcase
    end

    // ---------------- counters
    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 0; i < 7; i++) cnt[i] <= 16'd0;
            refused <= 32'd0;
        end else begin
            for (int i = 0; i < 7; i++) if (inc[i]) cnt[i] <= cnt[i] + 16'd1;
            if (|inc[6:1]) refused <= refused + 32'd1;
        end
    end

    // ---------------- packet receive / judge / execute / reply build
    logic       in_wr;
    assign in_wr = win_wr && (win_addr == 7'd0) && (st == S_IDLE);

    logic [31:0] fin;
    assign fin = ~crc;

    always_ff @(posedge clk) begin
        // datapath (no reset)
        if (in_wr && !nb[4]) pbuf[nb[3:0]] <= win_wdata[7:0];
        if (in_wr && win_wdata[8]) plen <= (nb == 5'd31) ? 5'd31 : nb + 5'd1;

        case (st)
            S_JUDGE: if (!(j_short1 || j_long || j_short2)) begin
                crc  <= CRC_INIT;
                cidx <= 5'd0;
            end
            S_CRC: if (cidx != plen) begin
                crc  <= crc8(crc, pbuf[cidx[3:0]]);
                cidx <= cidx + 5'd1;
            end
            S_EXEC: begin
                rbuf[0] <= typ | 8'h80;
                rbuf[1] <= {5'b0, status};
                rbuf[2] <= pbuf[2];
                rbuf[3] <= pbuf[3];
                rbuf[4] <= 8'd0;
                rm      <= 5'd5;
                crc     <= CRC_INIT;
                cidx    <= 5'd0;
                if (status == 3'd0) begin
                    if (typ == 8'd1) begin
                        rbuf[4] <= 8'd4;
                        rbuf[5] <= rval[31:24];
                        rbuf[6] <= rval[23:16];
                        rbuf[7] <= rval[15:8];
                        rbuf[8] <= rval[7:0];
                        rm      <= 5'd9;
                    end else if (typ == 8'd3) begin
                        rbuf[4] <= 8'd17;
                        for (int i = 0; i < 7; i++) begin
                            rbuf[5 + 2 * i] <= cnt[i][15:8];
                            rbuf[6 + 2 * i] <= cnt[i][7:0];
                        end
                        rbuf[19] <= fcnt[15:8];
                        rbuf[20] <= fcnt[7:0];
                        rbuf[21] <= {7'b0, tel_on};
                        rm       <= 5'd22;
                    end
                end
            end
            S_RCRC: if (cidx == rm) begin
                rbuf[rm]         <= fin[7:0];
                rbuf[rm + 5'd1]  <= fin[15:8];
                rbuf[rm + 5'd2]  <= fin[23:16];
                rbuf[rm + 5'd3]  <= fin[31:24];
            end else begin
                crc  <= crc8(crc, rbuf[cidx]);
                cidx <= cidx + 5'd1;
            end
            default: ;
        endcase

        // control
        if (rst) begin
            st        <= S_IDLE;
            nb        <= 5'd0;
            rlen      <= 5'd0;
            last      <= 16'd0;
            have_last <= 1'b0;
            for (int i = 0; i < 3; i++) scratch[i] <= 32'd0;
        end else begin
            case (st)
                S_IDLE: if (in_wr) begin
                    if (win_wdata[8]) begin
                        nb <= 5'd0;
                        st <= S_JUDGE;
                    end else if (nb != 5'd31) nb <= nb + 5'd1;
                end
                S_JUDGE: begin
                    rlen <= 5'd0;
                    if (j_short1 || j_long || j_short2) st <= S_IDLE;
                    else                                st <= S_CRC;
                end
                S_CRC: if (cidx == plen) begin
                    st <= (crc == CRC_RESIDUE) ? S_EXEC : S_IDLE;
                end
                S_EXEC: begin
                    st <= S_RCRC;
                    if (status != 3'd1 && status != 3'd2 && status != 3'd4) begin
                        last      <= seqn;
                        have_last <= 1'b1;
                    end
                    if (status == 3'd0 && typ == 8'd2) begin
                        case (p0[1:0])
                            2'd1: scratch[0] <= {pbuf[5], pbuf[6], pbuf[7], pbuf[8]};
                            2'd2: scratch[1] <= {pbuf[5], pbuf[6], pbuf[7], pbuf[8]};
                            2'd3: scratch[2] <= {pbuf[5], pbuf[6], pbuf[7], pbuf[8]};
                            default: ;
                        endcase
                    end
                end
                S_RCRC: if (cidx == rm) begin
                    rlen <= rm + 5'd4;
                    st   <= S_IDLE;
                end
                default: st <= S_IDLE;
            endcase
        end
    end

    // ---------------- time ticks and telemetry
    logic        tick, take;
    logic [16:0] tc_n;
    logic        due;
    assign tick = (pend != 8'd0);
    assign take = win_wr && (win_addr == 7'd8);
    assign tc_n = {1'b0, tcount} + 17'd1;
    assign due  = tick && tel_on && (tc_n >= {1'b0, period});

    logic [31:0] ticks_n;
    assign ticks_n = ticks + 32'd1;

    always_ff @(posedge clk) begin
        // datapath: frame snapshot and byte-serial CRC (no reset)
        if (due && !held) begin
            tbuf[0]  <= 8'hC0;
            tbuf[1]  <= 8'h00;
            tbuf[2]  <= fcnt[15:8];
            tbuf[3]  <= fcnt[7:0];
            tbuf[4]  <= 8'd8;
            tbuf[5]  <= ticks_n[31:24];
            tbuf[6]  <= ticks_n[23:16];
            tbuf[7]  <= ticks_n[15:8];
            tbuf[8]  <= ticks_n[7:0];
            tbuf[9]  <= cnt[0][15:8];
            tbuf[10] <= cnt[0][7:0];
            tbuf[11] <= refused[15:8];
            tbuf[12] <= refused[7:0];
            tcrc     <= CRC_INIT;
            tci      <= 5'd0;
        end else if (tbusy) begin
            if (tci != 5'd13) begin
                tcrc <= crc8(tcrc, tbuf[tci]);
                tci  <= tci + 5'd1;
            end else begin
                tbuf[13] <= ~tcrc[7:0];
                tbuf[14] <= ~tcrc[15:8];
                tbuf[15] <= ~tcrc[23:16];
                tbuf[16] <= ~tcrc[31:24];
            end
        end

        if (rst) begin
            pend   <= 8'd0;
            ticks  <= 32'd0;
            tel_on <= 1'b0;
            held   <= 1'b0;
            tbusy  <= 1'b0;
            period <= DEF_PERIOD;
            tcount <= 16'd0;
            fcnt   <= 16'd0;
        end else begin
            // tick generator
            if (win_wr && (win_addr == 7'd1)) pend <= win_wdata[7:0];
            else if (tick)                    pend <= pend - 8'd1;
            if (tick) ticks <= ticks_n;

            // period counter
            if (tick && tel_on) begin
                if (tc_n >= {1'b0, period}) begin
                    tcount <= 16'd0;
                    if (!held) begin
                        held  <= 1'b1;
                        tbusy <= 1'b1;
                        fcnt  <= fcnt + 16'd1;
                    end
                end else tcount <= tc_n[15:0];
            end

            if (tbusy && tci == 5'd13) tbusy <= 1'b0;

            if (ex_start) begin
                tel_on <= 1'b1;
                tcount <= 16'd0;
                if ({pbuf[4], pbuf[5]} != 16'd0)
                    period <= ({pbuf[4], pbuf[5]} < MIN_PERIOD) ? MIN_PERIOD : {pbuf[4], pbuf[5]};
            end
            if (ex_stop) tel_on <= 1'b0;
            if (ex_stop || take) begin
                held  <= 1'b0;
                tbusy <= 1'b0;
            end
        end
    end

    // ---------------- window registers
    always_ff @(posedge clk) begin
        if (rst) begin
            ridx <= 7'd0;
            tidx <= 7'd0;
        end else if (win_wr) begin
            if (win_addr == 7'd3) ridx <= win_wdata[6:0];
            if (win_addr == 7'd6) tidx <= win_wdata[6:0];
        end
    end

    logic [4:0] tlen;
    assign tlen = (held && !tbusy) ? 5'd17 : 5'd0;

    logic [31:0] rword, tword;
    logic [8:0]  ri [0:3];
    logic [8:0]  ti [0:3];
    logic [7:0]  rbyte [0:3];
    logic [7:0]  tbyte [0:3];
    always_comb begin
        for (int k = 0; k < 4; k++) begin
            ri[k]    = {ridx, 2'b00} + 9'(k);
            ti[k]    = {tidx, 2'b00} + 9'(k);
            rbyte[k] = (ri[k] < {4'b0, rlen}) ? rbuf[ri[k][4:0]] : 8'd0;
            tbyte[k] = (ti[k] < {4'b0, tlen}) ? tbuf[(ti[k][4:0] > 5'd16) ? 5'd0 : ti[k][4:0]] : 8'd0;
        end
        rword = {rbyte[0], rbyte[1], rbyte[2], rbyte[3]};
        tword = {tbyte[0], tbyte[1], tbyte[2], tbyte[3]};
    end

    logic busy;
    assign busy = (nb != 5'd0) || (st != S_IDLE);

    always_ff @(posedge clk) begin
        if (win_rd) begin
            case (win_addr)
                7'd2:    win_rdata <= {27'b0, rlen};
                7'd3:    win_rdata <= {25'b0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= {27'b0, tlen};
                7'd6:    win_rdata <= {25'b0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'b0, busy, tel_on};
                default: win_rdata <= 32'd0;
            endcase
        end
    end
endmodule
