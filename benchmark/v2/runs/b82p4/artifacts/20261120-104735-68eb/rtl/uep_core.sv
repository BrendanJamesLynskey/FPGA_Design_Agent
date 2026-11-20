// uep_core: UDP-payload command and telemetry endpoint, window register side included.
// One clock, synchronous active-high reset. Packet bytes come through the IN register.
module uep_core #(
    parameter logic [31:0] ID_WORD           = 32'h55445031,
    parameter logic [15:0] TELE_PERIOD_RESET = 16'd100,
    parameter logic [15:0] TELE_PERIOD_MIN   = 16'd4
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,   // only bits 8:0 are used by this design
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    // CRC-32 (reflected 0xEDB88320) one byte; the register holds the un-inverted running value.
    function automatic logic [31:0] crc8(input logic [31:0] c, input logic [7:0] b);
        logic [31:0] x;
        x = c ^ {24'b0, b};
        for (int k = 0; k < 8; k++) begin
            x = x[0] ? ((x >> 1) ^ 32'hEDB88320) : (x >> 1);
        end
        return x;
    endfunction

    typedef enum logic [2:0] {S_IDLE, S_CLASS, S_CRC, S_CHK, S_EXEC, S_BUILD} state_t;
    state_t state;

    // packet receive
    logic [7:0]  pbuf [16];
    logic [7:0]  pn;        // bytes received so far, saturating
    logic [7:0]  rn;        // bytes of the finished packet
    logic [4:0]  ci;
    logic [31:0] crc;

    // reply
    logic [7:0]   rbuf [32];
    logic [5:0]   rlen;
    logic [4:0]   ri;
    logic [7:0]   r_status;
    logic [7:0]   r_plen;
    logic [135:0] pl;

    // endpoint state
    logic [31:0] scr1, scr2, scr3;
    logic [15:0] cmds, c_bad, c_short, c_long, c_rep, c_ooo, c_err;
    logic [31:0] refused;
    logic        have_last;
    logic [15:0] last;
    logic [15:0] period;
    logic        tele_on;
    logic [15:0] tcount;
    logic [31:0] ticks;
    logic [15:0] pend;
    logic [15:0] fseq, fcount;
    logic        held, tbusy;
    logic [4:0]  tci;
    logic [31:0] tcrc;
    logic [135:0] fbv;       // frame byte j at [8*(16-j) +: 8]
    logic [6:0]  ridx, tidx;

    assign led = cmds;

    // ---------------- decision (combinational) ----------------
    logic [7:0]  ln, typ, reg_n;
    logic [15:0] seq;
    logic [8:0]  full_len;
    logic [4:0]  bl;
    logic [7:0]  need;
    logic        known, seq_ok;
    logic [15:0] seq_d;
    logic [7:0]  ex_status;
    logic [31:0] regval;
    logic [31:0] trailer;
    logic        crc_good;

    always_comb begin
        ln       = pbuf[1];
        typ      = pbuf[0];
        reg_n    = pbuf[4];
        seq      = {pbuf[2], pbuf[3]};
        full_len = 9'd8 + {1'b0, ln};
        bl       = 5'd4 + ln[4:0];
        case (typ)
            8'd1:    need = 8'd2;
            8'd2:    need = 8'd6;
            8'd4:    need = 8'd2;
            default: need = 8'd0;
        endcase
        known   = (typ >= 8'd1) && (typ <= 8'd5);
        seq_d   = seq - last;
        seq_ok  = !have_last || ((seq_d != 16'd0) && !seq_d[15]);
        if (!known)                                     ex_status = 8'd1;
        else if (ln != need)                            ex_status = 8'd2;
        else if (!seq_ok)                               ex_status = 8'd4;
        else if ((typ <= 8'd2) && (reg_n >= 8'd8))      ex_status = 8'd3;
        else if ((typ == 8'd2) && ((reg_n == 8'd0) || (reg_n >= 8'd4))) ex_status = 8'd5;
        else                                            ex_status = 8'd0;
        case (reg_n[2:0])
            3'd0:    regval = ID_WORD;
            3'd1:    regval = scr1;
            3'd2:    regval = scr2;
            3'd3:    regval = scr3;
            3'd4:    regval = {16'b0, cmds};
            3'd5:    regval = refused;
            3'd6:    regval = {16'b0, period};
            default: regval = ticks;
        endcase
        trailer  = {pbuf[bl[3:0] + 4'd3], pbuf[bl[3:0] + 4'd2], pbuf[bl[3:0] + 4'd1], pbuf[bl[3:0]]};
        crc_good = (~crc) == trailer;
    end

    // ---------------- ticks ----------------
    logic        tick;
    logic [15:0] tcnt_n;
    logic [16:0] pend_n;
    logic [16:0] add_n;
    assign tick   = (pend != 16'd0);
    assign tcnt_n = tcount + 16'd1;
    assign add_n  = (win_wr && (win_addr == 7'd1)) ? {9'b0, win_wdata[7:0]} : 17'd0;
    assign pend_n = {1'b0, pend} + add_n - (tick ? 17'd1 : 17'd0);

    // ---------------- reply byte selection ----------------
    logic [4:0]  body_len;
    logic [4:0]  pj;
    logic [4:0]  rt;
    logic [4:0]  tsh;
    logic [7:0]  rb;
    logic [7:0]  tb;
    logic [31:0] fcrc;
    always_comb begin
        body_len = 5'd5 + r_plen[4:0];
        pj       = ri - 5'd5;
        rt       = ri - body_len;
        tsh      = {rt[1:0], 3'b000};
        fcrc     = ~crc;
        tb       = fcrc[tsh +: 8];
        case (ri)
            5'd0:    rb = typ | 8'h80;
            5'd1:    rb = r_status;
            5'd2:    rb = pbuf[2];
            5'd3:    rb = pbuf[3];
            5'd4:    rb = r_plen;
            default: rb = pl[{(5'd16 - pj), 3'b000} +: 8];
        endcase
    end

    // ---------------- main sequential block ----------------
    always_ff @(posedge clk) begin
        if (rst) begin
            state     <= S_IDLE;
            pn        <= 8'd0;
            rn        <= 8'd0;
            ci        <= 5'd0;
            crc       <= 32'hFFFFFFFF;
            rlen      <= 6'd0;
            ri        <= 5'd0;
            r_status  <= 8'd0;
            r_plen    <= 8'd0;
            pl        <= '0;
            scr1      <= 32'd0;
            scr2      <= 32'd0;
            scr3      <= 32'd0;
            cmds      <= 16'd0;
            c_bad     <= 16'd0;
            c_short   <= 16'd0;
            c_long    <= 16'd0;
            c_rep     <= 16'd0;
            c_ooo     <= 16'd0;
            c_err     <= 16'd0;
            refused   <= 32'd0;
            have_last <= 1'b0;
            last      <= 16'd0;
            period    <= TELE_PERIOD_RESET;
            tele_on   <= 1'b0;
            tcount    <= 16'd0;
            ticks     <= 32'd0;
            pend      <= 16'd0;
            fseq      <= 16'd0;
            fcount    <= 16'd0;
            held      <= 1'b0;
            tbusy     <= 1'b0;
            tci       <= 5'd0;
            tcrc      <= 32'hFFFFFFFF;
            fbv       <= '0;
            ridx      <= 7'd0;
            tidx      <= 7'd0;
        end else begin
            // ---- ticks and telemetry due ----
            pend <= pend_n[16] ? 16'hFFFF : pend_n[15:0];
            if (tick) begin
                ticks <= ticks + 32'd1;
                if (tele_on) begin
                    tcount <= tcnt_n;
                    if (tcnt_n >= period) begin
                        tcount <= 16'd0;
                        if (!held) begin
                            held   <= 1'b1;
                            tbusy  <= 1'b1;
                            tci    <= 5'd0;
                            tcrc   <= 32'hFFFFFFFF;
                            fseq   <= fseq + 16'd1;
                            fcount <= fcount + 16'd1;
                            fbv[135:32] <= {8'hC0, 8'h00, fseq, 8'h08, ticks + 32'd1, cmds, refused[15:0]};
                        end
                    end
                end
            end

            // ---- frame CRC ----
            if (tbusy) begin
                if (tci < 5'd13) begin
                    tcrc <= crc8(tcrc, fbv[{(5'd16 - tci), 3'b000} +: 8]);
                    tci  <= tci + 5'd1;
                end else begin
                    fbv[31:0] <= {~tcrc[7:0], ~tcrc[15:8], ~tcrc[23:16], ~tcrc[31:24]};
                    tbusy     <= 1'b0;
                end
            end

            // ---- packet engine ----
            case (state)
                S_IDLE: begin
                    if (win_wr && (win_addr == 7'd0)) begin
                        if (pn < 8'd16) pbuf[pn[3:0]] <= win_wdata[7:0];
                        if (win_wdata[8]) begin
                            rn    <= (pn == 8'hFF) ? 8'hFF : pn + 8'd1;
                            pn    <= 8'd0;
                            rlen  <= 6'd0;
                            state <= S_CLASS;
                        end else if (pn != 8'hFF) begin
                            pn <= pn + 8'd1;
                        end
                    end
                end
                S_CLASS: begin
                    ci  <= 5'd0;
                    crc <= 32'hFFFFFFFF;
                    if (rn < 8'd4) begin
                        c_short <= c_short + 16'd1;
                        refused <= refused + 32'd1;
                        state   <= S_IDLE;
                    end else if ((ln > 8'd8) || ({1'b0, rn} > full_len)) begin
                        c_long  <= c_long + 16'd1;
                        refused <= refused + 32'd1;
                        state   <= S_IDLE;
                    end else if ({1'b0, rn} < full_len) begin
                        c_short <= c_short + 16'd1;
                        refused <= refused + 32'd1;
                        state   <= S_IDLE;
                    end else begin
                        state <= S_CRC;
                    end
                end
                S_CRC: begin
                    crc <= crc8(crc, pbuf[ci[3:0]]);
                    ci  <= ci + 5'd1;
                    if (ci == bl - 5'd1) state <= S_CHK;
                end
                S_CHK: begin
                    if (crc_good) begin
                        state <= S_EXEC;
                    end else begin
                        c_bad   <= c_bad + 16'd1;
                        refused <= refused + 32'd1;
                        state   <= S_IDLE;
                    end
                end
                S_EXEC: begin
                    state    <= S_BUILD;
                    ri       <= 5'd0;
                    crc      <= 32'hFFFFFFFF;
                    r_status <= ex_status;
                    r_plen   <= 8'd0;
                    pl       <= '0;
                    if ((ex_status == 8'd0) || (ex_status == 8'd3) || (ex_status == 8'd5)) begin
                        have_last <= 1'b1;
                        last      <= seq;
                    end
                    if (ex_status == 8'd0) begin
                        cmds <= cmds + 16'd1;
                        case (typ)
                            8'd1: begin
                                r_plen <= 8'd4;
                                pl     <= {regval, 104'b0};
                            end
                            8'd2: begin
                                case (reg_n[1:0])
                                    2'd1:    scr1 <= {pbuf[6], pbuf[7], pbuf[8], pbuf[9]};
                                    2'd2:    scr2 <= {pbuf[6], pbuf[7], pbuf[8], pbuf[9]};
                                    default: scr3 <= {pbuf[6], pbuf[7], pbuf[8], pbuf[9]};
                                endcase
                            end
                            8'd3: begin
                                r_plen <= 8'd17;
                                pl     <= {cmds, c_bad, c_short, c_long, c_rep, c_ooo, c_err, fcount,
                                           7'b0, tele_on};
                            end
                            8'd4: begin
                                if ({pbuf[4], pbuf[5]} != 16'd0)
                                    period <= ({pbuf[4], pbuf[5]} < TELE_PERIOD_MIN) ? TELE_PERIOD_MIN
                                                                                     : {pbuf[4], pbuf[5]};
                                tele_on <= 1'b1;
                                tcount  <= 16'd0;
                            end
                            default: begin  // 5: stop
                                tele_on <= 1'b0;
                                held    <= 1'b0;
                                tbusy   <= 1'b0;
                            end
                        endcase
                    end else begin
                        refused <= refused + 32'd1;
                        case (ex_status)
                            8'd4:    if (seq_d == 16'd0) c_rep <= c_rep + 16'd1;
                                     else                c_ooo <= c_ooo + 16'd1;
                            default: c_err <= c_err + 16'd1;
                        endcase
                    end
                end
                S_BUILD: begin
                    ri <= ri + 5'd1;
                    if (ri < body_len) begin
                        rbuf[ri] <= rb;
                        crc      <= crc8(crc, rb);
                    end else begin
                        rbuf[ri] <= tb;
                        if (rt == 5'd3) begin
                            rlen  <= {1'b0, ri} + 6'd1;
                            state <= S_IDLE;
                        end
                    end
                end
                default: state <= S_IDLE;
            endcase

            // ---- window writes (other registers) ----
            if (win_wr) begin
                case (win_addr)
                    7'd3:    ridx <= win_wdata[6:0];
                    7'd6:    tidx <= win_wdata[6:0];
                    7'd8:    begin held <= 1'b0; tbusy <= 1'b0; end
                    default: ;
                endcase
            end
        end
    end

    // ---------------- window reads ----------------
    logic        tvis;
    logic [8:0]  rj0, rj1, rj2, rj3, tj0, tj1, tj2, tj3;
    logic [31:0] rword, tword;
    assign tvis = held && !tbusy;

    function automatic logic [7:0] fbyte(input logic [135:0] v, input logic [8:0] j, input logic vis);
        logic [4:0] jj;
        jj = j[4:0];
        if (vis && (j < 9'd17)) fbyte = v[{(5'd16 - jj), 3'b000} +: 8];
        else                    fbyte = 8'd0;
    endfunction

    always_comb begin
        rj0 = {ridx, 2'b00};
        rj1 = {ridx, 2'b00} + 9'd1;
        rj2 = {ridx, 2'b00} + 9'd2;
        rj3 = {ridx, 2'b00} + 9'd3;
        tj0 = {tidx, 2'b00};
        tj1 = {tidx, 2'b00} + 9'd1;
        tj2 = {tidx, 2'b00} + 9'd2;
        tj3 = {tidx, 2'b00} + 9'd3;
        rword = {(({3'b0, rlen} > rj0) ? rbuf[rj0[4:0]] : 8'd0),
                 (({3'b0, rlen} > rj1) ? rbuf[rj1[4:0]] : 8'd0),
                 (({3'b0, rlen} > rj2) ? rbuf[rj2[4:0]] : 8'd0),
                 (({3'b0, rlen} > rj3) ? rbuf[rj3[4:0]] : 8'd0)};
        tword = {fbyte(fbv, tj0, tvis), fbyte(fbv, tj1, tvis), fbyte(fbv, tj2, tvis), fbyte(fbv, tj3, tvis)};
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            win_rdata <= 32'd0;
        end else if (win_rd) begin
            case (win_addr)
                7'd2:    win_rdata <= {26'b0, rlen};
                7'd3:    win_rdata <= {25'b0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= tvis ? 32'd17 : 32'd0;
                7'd6:    win_rdata <= {25'b0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'b0, (state != S_IDLE), tele_on};
                default: win_rdata <= 32'd0;
            endcase
        end
    end
endmodule
