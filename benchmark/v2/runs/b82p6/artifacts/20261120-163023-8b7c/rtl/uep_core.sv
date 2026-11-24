// uep_core: packet parser, register file, reply builder, telemetry and window registers.
// Packet types (spec): 1 read, 2 write, 3 telemetry start, 4 status, 5 telemetry stop.
// Payload: read {reg, x}, write {reg, value32 (4 bytes), x}, start {period16 high byte first}.
module uep_core #(
    parameter logic [31:0] ID_WORD                = 32'h55445031,
    parameter int          TELEMETRY_PERIOD_RESET = 100,
    parameter int          TELEMETRY_PERIOD_MIN   = 4
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

    // Bytewise reflected CRC-32 (zlib / Ethernet), no final xor.
    function automatic logic [31:0] crc8(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] r;
        r = c ^ {24'h0, d};
        for (int i = 0; i < 8; i++) r = r[0] ? ((r >> 1) ^ 32'hEDB8_8320) : (r >> 1);
        return r;
    endfunction

    typedef enum logic [1:0] {S_IDLE, S_J1, S_EXEC, S_CRC} st_t;
    st_t st;

    // ---- packet input
    logic [7:0]  pbuf [0:15];
    logic [7:0]  cnt;
    logic [31:0] pcrc;
    // judgement flags
    logic f_long, f_short, f_bad, f_typok, f_lenok, f_seqbad, f_seqeq, f_regbad, f_ro, f_rw, f_wr;

    // ---- state
    logic [15:0] c_bad, c_short, c_long, c_rep, c_ooo, c_err, carried, refused;
    logic [31:0] scr1, scr2, scr3;
    logic [15:0] last_seq;
    logic        have_seq;
    logic [15:0] period, tcount, fcount;
    logic [15:0] fseq;
    logic        tel_on, held, tbuild;
    logic [31:0] ticks;
    logic [7:0]  pend;
    logic [4:0]  tci;
    logic [31:0] tcrc;
    logic [7:0]  tbuf [0:31];
    logic [7:0]  rbuf [0:31];
    logic [5:0]  rlen, rbody, ci;
    logic [31:0] rcrc;
    logic [6:0]  ridx, tidx;

    // ---- judgement priority
    localparam logic [3:0] K_LONG = 4'd0, K_SHORT = 4'd1, K_BAD = 4'd2, K_TYPE = 4'd3, K_LEN = 4'd4,
                           K_SEQ = 4'd5, K_REG = 4'd6, K_RO = 4'd7, K_OK = 4'd8;
    logic [3:0] kind;
    always_comb begin
        if (f_long)                       kind = K_LONG;
        else if (f_short)                 kind = K_SHORT;
        else if (f_bad)                   kind = K_BAD;
        else if (!f_typok)                kind = K_TYPE;
        else if (!f_lenok)                kind = K_LEN;
        else if (have_seq && f_seqbad)    kind = K_SEQ;
        else if (f_rw && f_regbad)        kind = K_REG;
        else if (f_wr && f_ro)            kind = K_RO;
        else                              kind = K_OK;
    end

    logic [7:0]  typ;
    logic [15:0] seq;
    assign typ = pbuf[0];
    assign seq = {pbuf[2], pbuf[3]};

    logic [15:0] regnum, new_per;
    assign regnum  = {8'h0, pbuf[4]};
    assign new_per = {pbuf[4], pbuf[5]};

    logic [31:0] regval;
    always_comb begin
        case (regnum[2:0])
            3'd0:    regval = ID_WORD;
            3'd1:    regval = scr1;
            3'd2:    regval = scr2;
            3'd3:    regval = scr3;
            3'd4:    regval = {16'h0, carried};
            3'd5:    regval = {16'h0, refused};
            3'd6:    regval = {16'h0, period};
            default: regval = ticks;
        endcase
    end

    logic [3:0] status_code;
    always_comb begin
        case (kind)
            K_TYPE:  status_code = 4'd1;
            K_LEN:   status_code = 4'd2;
            K_REG:   status_code = 4'd3;
            K_SEQ:   status_code = 4'd4;
            K_RO:    status_code = 4'd5;
            default: status_code = 4'd0;
        endcase
    end

    logic [31:0] ticks_n;
    assign ticks_n = ticks + 32'd1;

    logic [31:0] rcrc_fin, tcrc_fin;
    assign rcrc_fin = ~rcrc;
    assign tcrc_fin = ~tcrc;

    // ---- word read-out
    logic [31:0] rword, tword;
    logic [4:0]  rbi;
    logic [5:0]  tbi;
    always_comb begin
        rword = 32'h0;
        rbi   = 5'h0;
        if (ridx[6:3] == 4'h0) begin
            for (int k = 0; k < 4; k++) begin
                rbi = {ridx[2:0], 2'(k)};
                if ({1'b0, rbi} < rlen) rword[31 - 8*k -: 8] = rbuf[rbi];
            end
        end
    end
    always_comb begin
        tword = 32'h0;
        tbi   = 6'h0;
        if (held && tidx[6:3] == 4'h0)
            for (int k = 0; k < 4; k++) begin
                tbi = {1'b0, tidx[2:0], 2'(k)};
                if (tbi < 6'd17) tword[31 - 8*k -: 8] = tbuf[tbi[4:0]];
            end
    end

    // ---- main sequential block
    always_ff @(posedge clk) begin
        if (rst) begin
            st <= S_IDLE;
            cnt <= 8'h0;
            c_bad <= '0; c_short <= '0; c_long <= '0; c_rep <= '0; c_ooo <= '0; c_err <= '0;
            carried <= '0; refused <= '0;
            scr1 <= '0; scr2 <= '0; scr3 <= '0;
            last_seq <= '0; have_seq <= 1'b0;
            period <= 16'(TELEMETRY_PERIOD_RESET);
            tcount <= '0; fcount <= '0; fseq <= '0;
            tel_on <= 1'b0; held <= 1'b0; tbuild <= 1'b0;
            ticks <= '0; pend <= '0;
            rlen <= '0; ridx <= '0; tidx <= '0;
            win_rdata <= '0;
            tci <= '0; ci <= '0; rbody <= '0;
        end else begin
            // ---------------- window writes
            if (win_wr) begin
                case (win_addr)
                    7'd0: if (st == S_IDLE) begin
                        if (cnt < 8'd16) pbuf[cnt[3:0]] <= win_wdata[7:0];
                        pcrc <= crc8((cnt == 8'h0) ? CRC_INIT : pcrc, win_wdata[7:0]);
                        if (cnt != 8'hFF) cnt <= cnt + 8'd1;
                        if (win_wdata[8]) begin
                            st <= S_J1;
                            rlen <= '0;
                        end
                    end
                    7'd3: ridx <= win_wdata[6:0];
                    7'd6: tidx <= win_wdata[6:0];
                    default: ;
                endcase
            end

            // ---------------- tick source
            if (pend != 8'h0) pend <= pend - 8'd1;
            if (win_wr && win_addr == 7'd1) pend <= win_wdata[7:0];

            // ---------------- telemetry frame builder
            if (tbuild) begin
                if (tci == 5'd13) begin
                    tbuf[13] <= tcrc_fin[7:0];
                    tbuf[14] <= tcrc_fin[15:8];
                    tbuf[15] <= tcrc_fin[23:16];
                    tbuf[16] <= tcrc_fin[31:24];
                    tbuild <= 1'b0;
                end else begin
                    tcrc <= crc8(tcrc, tbuf[tci]);
                    tci <= tci + 5'd1;
                end
            end

            // ---------------- ticks and telemetry due
            if (pend != 8'h0) begin
                ticks <= ticks_n;
                if (tel_on) begin
                    if (tcount + 16'd1 >= period) begin
                        tcount <= 16'h0;
                        if (!held) begin
                            held <= 1'b1;
                            tbuild <= 1'b1;
                            tci <= 5'h0;
                            tcrc <= CRC_INIT;
                            fseq <= fseq + 16'd1;
                            fcount <= fcount + 16'd1;
                            tbuf[0] <= 8'hC0;
                            tbuf[1] <= 8'h00;
                            tbuf[2] <= fseq[15:8];
                            tbuf[3] <= fseq[7:0];
                            tbuf[4] <= 8'h08;
                            tbuf[5] <= ticks_n[31:24];
                            tbuf[6] <= ticks_n[23:16];
                            tbuf[7] <= ticks_n[15:8];
                            tbuf[8] <= ticks_n[7:0];
                            tbuf[9] <= carried[15:8];
                            tbuf[10] <= carried[7:0];
                            tbuf[11] <= refused[15:8];
                            tbuf[12] <= refused[7:0];
                        end
                    end else begin
                        tcount <= tcount + 16'd1;
                    end
                end
            end

            // ---------------- take
            if (win_wr && win_addr == 7'd8) begin
                held <= 1'b0;
                tbuild <= 1'b0;
            end

            // ---------------- packet judgement, step 1: flags
            if (st == S_J1) begin
                f_long   <= (cnt >= 8'd2) && ((pbuf[1] > 8'd8) || ({1'b0, cnt} > (9'd8 + {1'b0, pbuf[1]})));
                f_short  <= (cnt < 8'd4) || ({1'b0, cnt} < (9'd8 + {1'b0, pbuf[1]}));
                f_bad    <= (pcrc != CRC_RESIDUE);
                f_typok  <= (typ >= 8'd1) && (typ <= 8'd5);
                f_rw     <= (typ == 8'd1) || (typ == 8'd2);
                f_wr     <= (typ == 8'd2);
                f_lenok  <= (typ == 8'd1 && pbuf[1] == 8'd2) || (typ == 8'd2 && pbuf[1] == 8'd6) ||
                            (typ == 8'd3 && pbuf[1] == 8'd2) || (typ == 8'd4 && pbuf[1] == 8'd0) ||
                            (typ == 8'd5 && pbuf[1] == 8'd0);
                f_seqeq  <= (seq == last_seq);
                f_seqbad <= (seq == last_seq) || ((seq - last_seq) >= 16'd32768);
                f_regbad <= (regnum >= 16'd8);
                f_ro     <= (regnum == 16'd0) || (regnum >= 16'd4);
                cnt <= 8'h0;
                st <= S_EXEC;
            end

            // ---------------- packet judgement, step 2: act
            if (st == S_EXEC) begin
                if (kind != K_OK) refused <= refused + 16'd1;
                case (kind)
                    K_LONG:  c_long  <= c_long + 16'd1;
                    K_SHORT: c_short <= c_short + 16'd1;
                    K_BAD:   c_bad   <= c_bad + 16'd1;
                    K_SEQ:   if (f_seqeq) c_rep <= c_rep + 16'd1; else c_ooo <= c_ooo + 16'd1;
                    K_OK:    ;
                    default: c_err <= c_err + 16'd1;
                endcase
                if (kind >= K_REG) begin
                    last_seq <= seq;
                    have_seq <= 1'b1;
                end
                if (kind == K_OK) begin
                    carried <= carried + 16'd1;
                    case (typ)
                        8'd2: begin
                            case (regnum[1:0])
                                2'd1: scr1 <= {pbuf[5], pbuf[6], pbuf[7], pbuf[8]};
                                2'd2: scr2 <= {pbuf[5], pbuf[6], pbuf[7], pbuf[8]};
                                default: scr3 <= {pbuf[5], pbuf[6], pbuf[7], pbuf[8]};
                            endcase
                        end
                        8'd3: begin
                            if (new_per != 16'h0)
                                period <= (new_per < 16'(TELEMETRY_PERIOD_MIN)) ? 16'(TELEMETRY_PERIOD_MIN) : new_per;
                            tel_on <= 1'b1;
                            tcount <= 16'h0;
                        end
                        8'd5: begin
                            tel_on <= 1'b0;
                            held <= 1'b0;
                            tbuild <= 1'b0;
                        end
                        default: ;
                    endcase
                end
                if (kind >= K_TYPE) begin
                    rbuf[0] <= typ | 8'h80;
                    rbuf[1] <= {4'h0, status_code};
                    rbuf[2] <= pbuf[2];
                    rbuf[3] <= pbuf[3];
                    rbuf[4] <= 8'h0;
                    rbody   <= 6'd5;
                    if (kind == K_OK && typ == 8'd1) begin
                        rbuf[4] <= 8'd4;
                        rbuf[5] <= regval[31:24];
                        rbuf[6] <= regval[23:16];
                        rbuf[7] <= regval[15:8];
                        rbuf[8] <= regval[7:0];
                        rbody   <= 6'd9;
                    end
                    if (kind == K_OK && typ == 8'd4) begin
                        rbuf[4]  <= 8'd17;
                        rbuf[5]  <= carried[15:8];  rbuf[6]  <= carried[7:0];
                        rbuf[7]  <= c_bad[15:8];    rbuf[8]  <= c_bad[7:0];
                        rbuf[9]  <= c_short[15:8];  rbuf[10] <= c_short[7:0];
                        rbuf[11] <= c_long[15:8];   rbuf[12] <= c_long[7:0];
                        rbuf[13] <= c_rep[15:8];    rbuf[14] <= c_rep[7:0];
                        rbuf[15] <= c_ooo[15:8];    rbuf[16] <= c_ooo[7:0];
                        rbuf[17] <= c_err[15:8];    rbuf[18] <= c_err[7:0];
                        rbuf[19] <= fcount[15:8];   rbuf[20] <= fcount[7:0];
                        rbuf[21] <= {7'h0, tel_on};
                        rbody    <= 6'd22;
                    end
                    rcrc <= CRC_INIT;
                    ci   <= 6'h0;
                    st   <= S_CRC;
                end else begin
                    st <= S_IDLE;
                end
            end

            // ---------------- reply CRC
            if (st == S_CRC) begin
                if (ci == rbody) begin
                    rbuf[rbody[4:0]]         <= rcrc_fin[7:0];
                    rbuf[rbody[4:0] + 5'd1]  <= rcrc_fin[15:8];
                    rbuf[rbody[4:0] + 5'd2]  <= rcrc_fin[23:16];
                    rbuf[rbody[4:0] + 5'd3]  <= rcrc_fin[31:24];
                    rlen <= rbody + 6'd4;
                    st <= S_IDLE;
                end else begin
                    rcrc <= crc8(rcrc, rbuf[ci[4:0]]);
                    ci <= ci + 6'd1;
                end
            end

            // ---------------- window reads (registered, valid the cycle after win_rd)
            if (win_rd) begin
                case (win_addr)
                    7'd2: win_rdata <= {26'h0, rlen};
                    7'd3: win_rdata <= {25'h0, ridx};
                    7'd4: win_rdata <= rword;
                    7'd5: win_rdata <= held ? 32'd17 : 32'd0;
                    7'd6: win_rdata <= {25'h0, tidx};
                    7'd7: win_rdata <= tword;
                    7'd9: win_rdata <= {30'h0, (st != S_IDLE), tel_on};
                    default: win_rdata <= 32'h0;
                endcase
            end
        end
    end

    assign led = carried;
endmodule
