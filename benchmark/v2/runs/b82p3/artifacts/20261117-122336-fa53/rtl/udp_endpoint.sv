// udp_endpoint.sv: packet check, command execution, reply builder and telemetry.
// One clock domain, synchronous active-high reset.
// Window registers (win_addr): 0 IN, 1 TICK, 2 RLEN, 3 RIDX, 4 RWORD, 5 TLEN, 6 TIDX,
// 7 TWORD, 8 TAKE, 9 STAT.
//
// Register-number placement in read/write payloads (spec: read 2 bytes, write 6 bytes):
//   [r, v3..v0, pad] number in the first byte, value at payload 1..4 (golden model layout).
module udp_endpoint #(
    parameter logic [31:0] ID_WORD        = 32'h5544_5031,
    parameter logic [31:0] CRC_POLY       = 32'hEDB8_8320,
    parameter int          DEFAULT_PERIOD = 100,
    parameter int          MIN_PERIOD     = 4,
    parameter bit          LEGACY_LEN     = 1'b1   // also accept 1-byte read and 5-byte write payloads
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [8:0]  win_wdata,     // only bits 8:0 are used by any register
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    typedef enum logic [2:0] {S_IDLE, S_SIZE, S_CRC, S_CMP, S_EXEC, S_EMIT, S_TRAIL} st_t;
    typedef enum logic [1:0] {T_IDLE, T_BODY, T_TRAIL} tst_t;

    function automatic logic [31:0] crc8(input logic [31:0] c_in, input logic [7:0] b);
        logic [31:0] c;
        c = c_in ^ {24'd0, b};
        for (int i = 0; i < 8; i++) c = c[0] ? ((c >> 1) ^ CRC_POLY) : (c >> 1);
        return c;
    endfunction

    // ---------------------------------------------------------------- state
    st_t         st;
    tst_t        tst;
    logic [7:0]  pbuf [16];
    logic [7:0]  rbuf [32];
    logic [7:0]  tbuf [32];
    logic [5:0]  wcnt, ntot;
    logic [4:0]  kcnt, tk;
    logic [31:0] crc, tcrc;
    logic [7:0]  hd_typ, hd_stat;
    logic [15:0] hd_seq;
    logic [4:0]  plen;
    logic [135:0] pay;
    logic [103:0] tshift;
    logic [4:0]  rlen;

    logic [31:0] cmds, refused, ticks;
    logic [15:0] c_bad, c_short, c_long, c_rep, c_ooo, c_err;
    logic [15:0] last;
    logic        have_last;
    logic [31:0] scr [3];
    logic [15:0] period, tcount, fseq;
    logic        tlm_on, held;
    logic [7:0]  pending;
    logic [6:0]  ridx, tidx;

    assign led = cmds[15:0];

    // ---------------------------------------------------------------- command decode
    logic [7:0]  x_typ, x_ln, x_r, x_need;
    logic [15:0] x_seq, x_d;
    logic [2:0]  x_stat;
    logic [31:0] x_rv, x_val;
    logic        x_len_ok;

    assign x_typ = pbuf[0];
    assign x_ln  = pbuf[1];
    assign x_seq = {pbuf[2], pbuf[3]};
    assign x_d   = x_seq - last;
    assign x_r   = pbuf[4];
    assign x_val = {pbuf[5], pbuf[6], pbuf[7], pbuf[8]};

    always_comb begin
        case (x_typ)
            8'd1:    x_need = 8'd2;
            8'd2:    x_need = 8'd6;
            8'd3:    x_need = 8'd2;
            default: x_need = 8'd0;
        endcase
        x_len_ok = (x_ln == x_need) ||
                   (LEGACY_LEN && ((x_typ == 8'd1 && x_ln == 8'd1) || (x_typ == 8'd2 && x_ln == 8'd5)));
        x_stat = 3'd0;
        if (x_typ == 8'd0 || x_typ > 8'd5) x_stat = 3'd1;
        else if (!x_len_ok) x_stat = 3'd2;
        else if (have_last && (x_d == 16'd0 || x_d[15])) x_stat = 3'd4;
        else if ((x_typ == 8'd1 || x_typ == 8'd2) && x_r >= 8'd8) x_stat = 3'd3;
        else if (x_typ == 8'd2 && (x_r == 8'd0 || x_r > 8'd3)) x_stat = 3'd5;
        case (x_r[2:0])
            3'd0:    x_rv = ID_WORD;
            3'd1:    x_rv = scr[0];
            3'd2:    x_rv = scr[1];
            3'd3:    x_rv = scr[2];
            3'd4:    x_rv = cmds;
            3'd5:    x_rv = refused;
            3'd6:    x_rv = {16'd0, period};
            default: x_rv = ticks;
        endcase
    end

    // ---------------------------------------------------------------- readback words
    logic [8:0]  rbase, tbase;
    logic [31:0] rword, tword;
    logic [8:0]  tlen;
    assign tlen  = held ? 9'd17 : 9'd0;
    assign rbase = {ridx, 2'b00};
    assign tbase = {tidx, 2'b00};
    always_comb begin
        logic [8:0] j;
        for (int k = 0; k < 4; k++) begin
            j = rbase + 9'(k);
            rword[31 - 8*k -: 8] = (j < {4'd0, rlen}) ? rbuf[j[4:0]] : 8'd0;
            j = tbase + 9'(k);
            tword[31 - 8*k -: 8] = (j < tlen) ? tbuf[j[4:0]] : 8'd0;
        end
    end

    logic busy;
    assign busy = (st != S_IDLE);

    logic [31:0] rd_mux;
    always_comb begin
        case (win_addr)
            7'd2:    rd_mux = {27'd0, rlen};
            7'd3:    rd_mux = {25'd0, ridx};
            7'd4:    rd_mux = rword;
            7'd5:    rd_mux = {23'd0, tlen};
            7'd6:    rd_mux = {25'd0, tidx};
            7'd7:    rd_mux = tword;
            7'd9:    rd_mux = {30'd0, busy, tlm_on};
            default: rd_mux = 32'd0;
        endcase
    end

    always_ff @(posedge clk) begin
        if (win_rd) win_rdata <= rd_mux;
    end

    // ---------------------------------------------------------------- emit byte
    logic [7:0] e_byte;
    always_comb begin
        case (kcnt)
            5'd0:    e_byte = hd_typ;
            5'd1:    e_byte = hd_stat;
            5'd2:    e_byte = hd_seq[15:8];
            5'd3:    e_byte = hd_seq[7:0];
            5'd4:    e_byte = {3'd0, plen};
            default: e_byte = pay[135:128];
        endcase
    end

    logic [31:0] ticks_n;
    logic [16:0] tcount_n;
    logic        tick;
    assign tick     = (pending != 8'd0);
    assign ticks_n  = ticks + 32'd1;
    assign tcount_n = {1'b0, tcount} + 17'd1;

    logic [31:0] trailer, ncrc, ntcrc;
    logic [3:0]  bl;
    assign bl      = x_ln[3:0] + 4'd4;
    assign trailer = {pbuf[bl + 4'd3], pbuf[bl + 4'd2], pbuf[bl + 4'd1], pbuf[bl]};
    assign ncrc    = ~crc;
    assign ntcrc   = ~tcrc;

    // ---------------------------------------------------------------- main sequential block
    always_ff @(posedge clk) begin
        // datapath (no reset)
        case (st)
            S_IDLE: begin
                if (win_wr && win_addr == 7'd0 && wcnt[5:4] == 2'd0)
                    pbuf[wcnt[3:0]] <= win_wdata[7:0];
            end
            S_CRC:  crc <= crc8(crc, pbuf[kcnt[3:0]]);
            S_EMIT: begin
                rbuf[kcnt] <= e_byte;
                crc        <= crc8(crc, e_byte);
                if (kcnt >= 5'd5) pay <= pay << 8;
            end
            S_TRAIL: begin
                rbuf[kcnt]        <= ncrc[7:0];
                rbuf[kcnt + 5'd1] <= ncrc[15:8];
                rbuf[kcnt + 5'd2] <= ncrc[23:16];
                rbuf[kcnt + 5'd3] <= ncrc[31:24];
            end
            default: ;
        endcase
        if (st == S_SIZE) begin
            crc  <= 32'hFFFF_FFFF;
            kcnt <= 5'd0;
        end
        if (st == S_EXEC) begin
            hd_typ  <= x_typ | 8'h80;
            hd_stat <= {5'd0, x_stat};
            hd_seq  <= x_seq;
            plen    <= 5'd0;
            pay     <= '0;
            crc     <= 32'hFFFF_FFFF;
            kcnt    <= 5'd0;
            if (x_stat == 3'd0) begin
                if (x_typ == 8'd1) begin
                    plen <= 5'd4;
                    pay  <= {x_rv, 104'd0};
                end
                if (x_typ == 8'd4) begin
                    plen <= 5'd17;
                    pay  <= {cmds[15:0], c_bad, c_short, c_long, c_rep, c_ooo, c_err, fseq,
                             7'd0, tlm_on};
                end
            end
        end
        if (st == S_EMIT || st == S_CRC) kcnt <= kcnt + 5'd1;

        // telemetry frame engine datapath
        case (tst)
            T_BODY: begin
                tbuf[tk] <= tshift[103:96];
                tcrc     <= crc8(tcrc, tshift[103:96]);
                tshift   <= tshift << 8;
                tk       <= tk + 5'd1;
            end
            T_TRAIL: begin
                tbuf[13] <= ntcrc[7:0];
                tbuf[14] <= ntcrc[15:8];
                tbuf[15] <= ntcrc[23:16];
                tbuf[16] <= ntcrc[31:24];
            end
            default: ;
        endcase

        if (rst) begin
            st        <= S_IDLE;
            tst       <= T_IDLE;
            wcnt      <= '0;
            ntot      <= '0;
            rlen      <= '0;
            cmds      <= '0;
            refused   <= '0;
            ticks     <= '0;
            c_bad     <= '0;
            c_short   <= '0;
            c_long    <= '0;
            c_rep     <= '0;
            c_ooo     <= '0;
            c_err     <= '0;
            last      <= '0;
            have_last <= 1'b0;
            for (int i = 0; i < 3; i++) scr[i] <= '0;
            period    <= 16'(DEFAULT_PERIOD);
            tcount    <= '0;
            fseq      <= '0;
            tlm_on    <= 1'b0;
            held      <= 1'b0;
            pending   <= '0;
            ridx      <= '0;
            tidx      <= '0;
        end else begin
            // ---- window writes
            if (win_wr) begin
                case (win_addr)
                    7'd1: pending <= win_wdata[7:0];
                    7'd3: ridx    <= win_wdata[6:0];
                    7'd6: tidx    <= win_wdata[6:0];
                    default: ;
                endcase
            end
            if (tick && !(win_wr && win_addr == 7'd1)) pending <= pending - 8'd1;

            // ---- telemetry frame engine control (a new due below overrides)
            if (tst == T_BODY) begin
                if (!held) tst <= T_IDLE;
                else if (tk == 5'd12) tst <= T_TRAIL;
            end
            if (tst == T_TRAIL) tst <= T_IDLE;

            // ---- ticks and telemetry due
            if (tick) begin
                ticks <= ticks_n;
                if (tlm_on) begin
                    if (tcount_n >= {1'b0, period}) begin
                        tcount <= '0;
                        if (!held) begin
                            held   <= 1'b1;
                            fseq   <= fseq + 16'd1;
                            tshift <= {8'hC0, 8'h00, fseq, 8'd8, ticks_n, cmds[15:0], refused[15:0]};
                            tst    <= T_BODY;
                            tk     <= 5'd0;
                            tcrc   <= 32'hFFFF_FFFF;
                        end
                    end else begin
                        tcount <= tcount_n[15:0];
                    end
                end
            end
            if (win_wr && win_addr == 7'd8) held <= 1'b0;

            // ---- packet reception and judging
            case (st)
                S_IDLE: begin
                    if (win_wr && win_addr == 7'd0) begin
                        if (win_wdata[8]) begin
                            ntot <= (wcnt == 6'd63) ? wcnt : wcnt + 6'd1;
                            wcnt <= '0;
                            rlen <= '0;
                            st   <= S_SIZE;
                        end else if (wcnt != 6'd63) begin
                            wcnt <= wcnt + 6'd1;
                        end
                    end
                end
                S_SIZE: begin
                    if (ntot < 6'd4) begin
                        c_short <= c_short + 16'd1;
                        refused <= refused + 32'd1;
                        st      <= S_IDLE;
                    end else if (x_ln > 8'd8 || {3'd0, ntot} > 9'd8 + {1'b0, x_ln}) begin
                        c_long  <= c_long + 16'd1;
                        refused <= refused + 32'd1;
                        st      <= S_IDLE;
                    end else if ({3'd0, ntot} < 9'd8 + {1'b0, x_ln}) begin
                        c_short <= c_short + 16'd1;
                        refused <= refused + 32'd1;
                        st      <= S_IDLE;
                    end else begin
                        st <= S_CRC;
                    end
                end
                S_CRC: begin
                    if ({3'd0, kcnt} == x_ln + 8'd3) st <= S_CMP;
                end
                S_CMP: begin
                    if (ncrc != trailer) begin
                        c_bad   <= c_bad + 16'd1;
                        refused <= refused + 32'd1;
                        st      <= S_IDLE;
                    end else begin
                        st <= S_EXEC;
                    end
                end
                S_EXEC: begin
                    st <= S_EMIT;
                    if (x_stat == 3'd1 || x_stat == 3'd2 || x_stat == 3'd3 || x_stat == 3'd5) begin
                        c_err <= c_err + 16'd1;
                    end else if (x_stat == 3'd4) begin
                        if (x_seq == last) c_rep <= c_rep + 16'd1;
                        else               c_ooo <= c_ooo + 16'd1;
                    end
                    if (x_stat != 3'd0) refused <= refused + 32'd1;
                    if (x_stat == 3'd0 || x_stat == 3'd3 || x_stat == 3'd5) begin
                        last      <= x_seq;
                        have_last <= 1'b1;
                    end
                    if (x_stat == 3'd0) begin
                        cmds <= cmds + 32'd1;
                        case (x_typ)
                            8'd2: scr[x_r[1:0] - 2'd1] <= x_val;
                            8'd3: begin
                                if (!(pbuf[4] == 8'd0 && pbuf[5] == 8'd0))
                                    period <= ({pbuf[4], pbuf[5]} < 16'(MIN_PERIOD))
                                              ? 16'(MIN_PERIOD) : {pbuf[4], pbuf[5]};
                                tlm_on <= 1'b1;
                                tcount <= '0;
                            end
                            8'd5: begin
                                tlm_on <= 1'b0;
                                held   <= 1'b0;
                            end
                            default: ;
                        endcase
                    end
                end
                S_EMIT: begin
                    if ({1'b0, kcnt} == {1'b0, plen} + 6'd4) st <= S_TRAIL;
                end
                S_TRAIL: begin
                    rlen <= kcnt + 5'd4;
                    st   <= S_IDLE;
                end
                default: st <= S_IDLE;
            endcase
        end
    end
endmodule
