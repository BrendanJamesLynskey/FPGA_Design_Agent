// uep_core: packet receiver, command executor, telemetry and readback window.
// One clock; synchronous active-high reset on control state only.
module uep_core #(
    parameter logic [31:0] ID_WORD      = 32'h55445031,
    parameter logic [15:0] PERIOD_RESET = 16'd100,
    parameter logic [15:0] PERIOD_MIN   = 16'd4
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
    typedef enum logic [2:0] {S_IDLE, S_DEC, S_CRC, S_CMP, S_EXEC, S_BLD, S_TRL} state_t;
    state_t state;

    // ------------------------------------------------------------ storage
    logic [7:0]  pbuf [0:15];   // command bytes
    logic [7:0]  rep  [0:31];   // latest reply
    logic [7:0]  tel  [0:16];   // held telemetry frame

    logic [7:0]  n, nlat, ci, hl;
    logic [1:0]  k;
    logic [31:0] crc, crc_nx;
    logic [7:0]  cbyte;
    logic [7:0]  rlen;
    logic [6:0]  ridx, tidx;

    logic [15:0] cnt [0:6];     // ok, badcrc, short, long, repeated, ooo, err
    logic [15:0] refused;
    logic [15:0] last_seq;
    logic        have_last;
    logic [31:0] scratch [0:2];

    // telemetry
    logic [31:0] ticks;
    logic [15:0] pending, tick_cnt, period, fseq;
    logic        tel_on, held, tb_busy;
    logic [4:0]  tci;
    logic [31:0] tcrc, tcrc_nx;

    // ------------------------------------------------------------ window decode
    logic wr_in, wr_tick, wr_take;
    assign wr_in   = win_wr && (win_addr == 7'd0);
    assign wr_tick = win_wr && (win_addr == 7'd1);
    assign wr_take = win_wr && (win_addr == 7'd8);

    logic [7:0] next_n;
    assign next_n = (n == 8'hFF) ? 8'hFF : n + 8'd1;

    logic busy;
    assign busy = (state != S_IDLE) || (n != 8'd0);

    // ------------------------------------------------------------ shared CRC engine
    assign cbyte = (state == S_BLD) ? rep[ci[4:0]] : pbuf[ci[3:0]];
    crc32_byte u_crc (.crc_in(crc), .data(cbyte), .crc_out(crc_nx));

    // ------------------------------------------------------------ decode (comb)
    logic [7:0]  typ, ln;
    logic [15:0] seq, r16, dseq;
    logic [31:0] wval;
    assign typ  = pbuf[0];
    assign ln   = pbuf[1];
    assign seq  = {pbuf[2], pbuf[3]};
    assign r16  = {pbuf[4], pbuf[5]};
    assign wval = {pbuf[6], pbuf[7], pbuf[8], pbuf[9]};
    assign dseq = seq - last_seq;

    logic [8:0] nl9, full9;
    assign nl9   = {1'b0, nlat};
    assign full9 = 9'd8 + {1'b0, ln};

    logic [3:0] n4;
    assign n4 = nlat[3:0];
    logic [31:0] trailer;
    assign trailer = {pbuf[n4 - 4'd1], pbuf[n4 - 4'd2], pbuf[n4 - 4'd3], pbuf[n4 - 4'd4]};
    logic crc_bad;
    assign crc_bad = (~crc) != trailer;

    logic        known, len_ok, seq_bad, seq_rep, pass_seq;
    logic [2:0]  status;
    logic [7:0]  want;
    always_comb begin
        known = 1'b1;
        want  = 8'd0;
        case (typ)
            8'd1:    want = 8'd2;
            8'd2:    want = 8'd6;
            8'd3:    want = 8'd0;
            8'd4:    want = 8'd2;
            8'd5:    want = 8'd0;
            default: known = 1'b0;
        endcase
        len_ok   = (ln == want);
        seq_rep  = (dseq == 16'd0);
        seq_bad  = have_last && (seq_rep || dseq[15]);
        pass_seq = known && len_ok && !seq_bad;
        status   = 3'd0;
        if (!known)        status = 3'd1;
        else if (!len_ok)  status = 3'd2;
        else if (seq_bad)  status = 3'd4;
        else if (typ == 8'd1 || typ == 8'd2) begin
            if (r16 >= 16'd8) status = 3'd3;
            else if (typ == 8'd2 && (r16 == 16'd0 || r16 >= 16'd4)) status = 3'd5;
        end
    end

    // register read value for a read command
    logic [31:0] regval;
    always_comb begin
        case (r16[2:0])
            3'd0:    regval = ID_WORD;
            3'd1:    regval = scratch[0];
            3'd2:    regval = scratch[1];
            3'd3:    regval = scratch[2];
            3'd4:    regval = {16'b0, cnt[0]};
            3'd5:    regval = {16'b0, refused};
            3'd6:    regval = {16'b0, period};
            default: regval = ticks;
        endcase
    end

    // reply payload
    logic [7:0] pay [0:16];
    logic [7:0] plen;
    always_comb begin
        for (int i = 0; i < 17; i++) pay[i] = 8'h00;
        plen = 8'd0;
        if (status == 3'd0 && typ == 8'd1) begin
            plen   = 8'd4;
            pay[0] = regval[31:24];
            pay[1] = regval[23:16];
            pay[2] = regval[15:8];
            pay[3] = regval[7:0];
        end else if (status == 3'd0 && typ == 8'd3) begin
            plen = 8'd17;
            for (int i = 0; i < 7; i++) begin
                pay[2*i]   = cnt[i][15:8];
                pay[2*i+1] = cnt[i][7:0];
            end
            pay[14] = fseq[15:8];
            pay[15] = fseq[7:0];
            pay[16] = {7'b0, tel_on};
        end
    end

    // refusal counting decisions
    logic       ref_en, ok_en;
    logic [2:0] ref_idx;
    always_comb begin
        ref_en  = 1'b0;
        ref_idx = 3'd0;
        ok_en   = 1'b0;
        case (state)
            S_DEC: begin
                if (nlat < 8'd4) begin
                    ref_en = 1'b1; ref_idx = 3'd2;
                end else if (ln > 8'd8 || nl9 > full9) begin
                    ref_en = 1'b1; ref_idx = 3'd3;
                end else if (nl9 < full9) begin
                    ref_en = 1'b1; ref_idx = 3'd2;
                end
            end
            S_CMP: begin
                if (crc_bad) begin
                    ref_en = 1'b1; ref_idx = 3'd1;
                end
            end
            S_EXEC: begin
                if (status != 3'd0) begin
                    ref_en  = 1'b1;
                    ref_idx = (status == 3'd4) ? (seq_rep ? 3'd4 : 3'd5) : 3'd6;
                end else begin
                    ok_en = 1'b1;
                end
            end
            default: ;
        endcase
    end

    logic x_start, x_stop;
    logic [15:0] per_eff;
    assign x_start = (state == S_EXEC) && (status == 3'd0) && (typ == 8'd4);
    assign x_stop  = (state == S_EXEC) && (status == 3'd0) && (typ == 8'd5);
    assign per_eff = (r16 < PERIOD_MIN) ? PERIOD_MIN : r16;

    // ------------------------------------------------------------ control state
    always_ff @(posedge clk) begin
        if (rst) begin
            state     <= S_IDLE;
            n         <= 8'd0;
            rlen      <= 8'd0;
            have_last <= 1'b0;
            last_seq  <= 16'd0;
            refused   <= 16'd0;
            ridx      <= 7'd0;
            tidx      <= 7'd0;
            for (int i = 0; i < 7; i++) cnt[i] <= 16'd0;
            for (int i = 0; i < 3; i++) scratch[i] <= 32'd0;
        end else begin
            if (win_wr && win_addr == 7'd3) ridx <= win_wdata[6:0];
            if (win_wr && win_addr == 7'd6) tidx <= win_wdata[6:0];

            if (ref_en) begin
                refused      <= refused + 16'd1;
                cnt[ref_idx] <= cnt[ref_idx] + 16'd1;
            end
            if (ok_en) cnt[0] <= cnt[0] + 16'd1;

            case (state)
                S_IDLE: if (wr_in) begin
                    if (win_wdata[8]) begin
                        n     <= 8'd0;
                        rlen  <= 8'd0;
                        state <= S_DEC;
                    end else begin
                        n <= next_n;
                    end
                end
                S_DEC:  state <= (ref_en) ? S_IDLE : S_CRC;
                S_CRC:  if (ci == nlat - 8'd5) state <= S_CMP;
                S_CMP:  state <= crc_bad ? S_IDLE : S_EXEC;
                S_EXEC: begin
                    if (pass_seq) begin
                        last_seq  <= seq;
                        have_last <= 1'b1;
                    end
                    if (status == 3'd0 && typ == 8'd2)
                        scratch[r16[1:0] - 2'd1] <= wval;
                    state <= S_BLD;
                end
                S_BLD:  if (ci == hl - 8'd1) state <= S_TRL;
                S_TRL:  if (k == 2'd3) begin
                    rlen  <= hl + 8'd4;
                    state <= S_IDLE;
                end
                default: state <= S_IDLE;
            endcase
        end
    end

    // ------------------------------------------------------------ datapath (no reset)
    logic [31:0] crc_fin;
    logic [7:0]  crc_byte_sel;
    assign crc_fin      = ~crc;
    assign crc_byte_sel = crc_fin[{k, 3'b000} +: 8];

    always_ff @(posedge clk) begin
        if (state == S_IDLE && wr_in) begin
            if (n < 8'd16) pbuf[n[3:0]] <= win_wdata[7:0];
            if (win_wdata[8]) nlat <= next_n;
        end
        case (state)
            S_DEC: begin
                crc <= 32'hFFFFFFFF;
                ci  <= 8'd0;
            end
            S_CRC: begin
                crc <= crc_nx;
                ci  <= ci + 8'd1;
            end
            S_EXEC: begin
                rep[0] <= {1'b1, typ[6:0]};
                rep[1] <= {5'b0, status};
                rep[2] <= seq[15:8];
                rep[3] <= seq[7:0];
                rep[4] <= plen;
                for (int i = 0; i < 17; i++) rep[5+i] <= pay[i];
                hl  <= 8'd5 + plen;
                crc <= 32'hFFFFFFFF;
                ci  <= 8'd0;
            end
            S_BLD: begin
                crc <= crc_nx;
                ci  <= ci + 8'd1;
                k   <= 2'd0;
            end
            S_TRL: begin
                rep[hl[4:0] + {3'b0, k}] <= crc_byte_sel;
                k <= k + 2'd1;
            end
            default: ;
        endcase
    end

    // ------------------------------------------------------------ telemetry
    crc32_byte u_tcrc (.crc_in(tcrc), .data(tel[tci]), .crc_out(tcrc_nx));

    logic tick, cnt_hit, due, clr_held, frame_go;
    assign tick     = (pending != 16'd0);
    assign cnt_hit  = ({1'b0, tick_cnt} + 17'd1) >= {1'b0, period};
    assign due      = tick && tel_on && cnt_hit;
    assign clr_held = wr_take || x_stop;
    assign frame_go = due && !held && !tb_busy && !clr_held;

    logic [31:0] up_now;
    assign up_now = ticks + 32'd1;

    always_ff @(posedge clk) begin
        if (rst) begin
            ticks    <= 32'd0;
            pending  <= 16'd0;
            tick_cnt <= 16'd0;
            period   <= PERIOD_RESET;
            tel_on   <= 1'b0;
            held     <= 1'b0;
            tb_busy  <= 1'b0;
            fseq     <= 16'd0;
        end else begin
            pending <= pending + (wr_tick ? {8'b0, win_wdata[7:0]} : 16'd0)
                               - (tick ? 16'd1 : 16'd0);
            if (tick) begin
                ticks <= up_now;
                if (tel_on) tick_cnt <= cnt_hit ? 16'd0 : tick_cnt + 16'd1;
            end
            if (frame_go) begin
                held    <= 1'b1;
                tb_busy <= 1'b1;
                fseq    <= fseq + 16'd1;
            end else if (tb_busy && tci == 5'd16) begin
                tb_busy <= 1'b0;
            end
            if (x_start) begin
                tel_on   <= 1'b1;
                tick_cnt <= 16'd0;
                if (r16 != 16'd0) period <= per_eff;
            end
            if (x_stop) tel_on <= 1'b0;
            if (clr_held) begin
                held    <= 1'b0;
                tb_busy <= 1'b0;
            end
        end
    end

    // frame byte index tci-13 (13..16 -> 0..3) is tci[1:0]-1 modulo 4
    logic [31:0] tcrc_fin;
    logic [7:0]  tfin_byte;
    logic [1:0]  tk;
    assign tcrc_fin  = ~tcrc;
    assign tk        = tci[1:0] - 2'd1;
    assign tfin_byte = tcrc_fin[{tk, 3'b000} +: 8];

    always_ff @(posedge clk) begin
        if (frame_go) begin
            tel[0]  <= 8'hC0;
            tel[1]  <= 8'h00;
            tel[2]  <= fseq[15:8];
            tel[3]  <= fseq[7:0];
            tel[4]  <= 8'd8;
            tel[5]  <= up_now[31:24];
            tel[6]  <= up_now[23:16];
            tel[7]  <= up_now[15:8];
            tel[8]  <= up_now[7:0];
            tel[9]  <= cnt[0][15:8];
            tel[10] <= cnt[0][7:0];
            tel[11] <= refused[15:8];
            tel[12] <= refused[7:0];
            tci     <= 5'd0;
            tcrc    <= 32'hFFFFFFFF;
        end else if (tb_busy) begin
            if (tci < 5'd13) begin
                tcrc <= tcrc_nx;
            end else begin
                tel[tci] <= tfin_byte;
            end
            tci <= tci + 5'd1;
        end
    end

    // ------------------------------------------------------------ readback window
    logic [31:0] rword, tword;
    always_comb begin
        for (int j = 0; j < 4; j++) begin
            logic [8:0] ri, ti;
            ri = {ridx, 2'b00} + 9'(j);
            ti = {tidx, 2'b00} + 9'(j);
            rword[31-8*j -: 8] = (ri < {1'b0, rlen}) ? rep[ri[4:0]] : 8'h00;
            tword[31-8*j -: 8] = (held && ti < 9'd17) ? tel[ti[4:0]] : 8'h00;
        end
    end

    always_ff @(posedge clk) begin
        if (win_rd) begin
            case (win_addr)
                7'd2:    win_rdata <= {24'b0, rlen};
                7'd3:    win_rdata <= {25'b0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= held ? 32'd17 : 32'd0;
                7'd6:    win_rdata <= {25'b0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'b0, busy, tel_on};
                default: win_rdata <= 32'd0;
            endcase
        end
    end

    assign led = cnt[0];
endmodule
