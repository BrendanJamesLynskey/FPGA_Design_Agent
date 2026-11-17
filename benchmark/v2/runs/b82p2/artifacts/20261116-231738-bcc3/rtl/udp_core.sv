// udp_core: packet receive, judging, execution, reply build, ticks and telemetry,
// behind the shell register window (offsets 0..9).
module udp_core #(
    parameter int          TIMEOUT_CYCLES       = 100_000_000,
    parameter logic [31:0] ID_WORD              = 32'h55445031,
    parameter int          DEFAULT_PERIOD_TICKS = 100,
    parameter int          MIN_PERIOD_TICKS     = 4
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,   // only bits 8:0 are used by this window
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    output logic [15:0] led
);
    localparam int IDLE_W = $clog2(TIMEOUT_CYCLES + 1);
    localparam logic [IDLE_W-1:0] TMO_LAST = IDLE_W'(TIMEOUT_CYCLES - 1);
    localparam logic [31:0] CRC_RESIDUE = 32'hDEBB20E3;
    localparam logic [15:0] DEF_PERIOD = 16'(DEFAULT_PERIOD_TICKS);
    localparam logic [15:0] MIN_PERIOD = 16'(MIN_PERIOD_TICKS);

    localparam logic [7:0] T_READ = 8'd1, T_WRITE = 8'd2, T_STATUS = 8'd3,
                           T_TSTART = 8'd4, T_TSTOP = 8'd5;

    typedef enum logic [2:0] {S_RX, S_J, S_CRC, S_CHK, S_EXEC, S_WAIT} st_t;
    st_t st;

    // ---------------------------------------------------------------- window decode
    logic in_wr, tick_wr, ridx_wr, tidx_wr, take_wr;
    assign in_wr   = win_wr && (win_addr == 7'd0);
    assign tick_wr = win_wr && (win_addr == 7'd1);
    assign ridx_wr = win_wr && (win_addr == 7'd3);
    assign tidx_wr = win_wr && (win_addr == 7'd6);
    assign take_wr = win_wr && (win_addr == 7'd8);

    // ---------------------------------------------------------------- state
    logic [7:0]  rbuf [0:15];
    logic [7:0]  nb;
    logic [IDLE_W-1:0] idle;
    logic [4:0]  ci;
    logic [31:0] crc, crc_nx;

    logic [31:0] scratch1, scratch2, scratch3;
    logic [15:0] cnt [0:6];
    logic [15:0] refused;
    logic [15:0] period;
    logic [31:0] ticks;
    logic [7:0]  pend;
    logic        tele_on;
    logic [15:0] tcnt;
    logic        held;
    logic [15:0] fseq, fcount;
    logic        have_last;
    logic [15:0] last_seq;
    logic [6:0]  ridx, tidx;
    logic [5:0]  rlen;

    // ---------------------------------------------------------------- receive-side decode
    logic [7:0] ln;
    logic [8:0] need9;
    logic       j_short1, j_long, j_short2, to_fire;
    assign ln       = rbuf[1];
    assign need9    = 9'd8 + {1'b0, ln};
    assign j_short1 = nb < 8'd4;
    assign j_long   = (ln > 8'd8) || ({1'b0, nb} > need9);
    assign j_short2 = {1'b0, nb} < need9;
    assign to_fire  = (st == S_RX) && (nb != 8'd0) && !in_wr && (idle >= TMO_LAST);

    // CRC over the received packet, trailer included: residue check
    crc32_byte u_crc (.c(crc), .d(rbuf[ci[3:0]]), .n(crc_nx));

    always_ff @(posedge clk) begin
        if (st == S_J) begin
            ci  <= 5'd0;
            crc <= 32'hFFFFFFFF;
        end else if (st == S_CRC) begin
            ci  <= ci + 5'd1;
            crc <= crc_nx;
        end
    end

    always_ff @(posedge clk) begin
        if (st == S_RX && in_wr && nb < 8'd16) rbuf[nb[3:0]] <= win_wdata[7:0];
    end

    // ---------------------------------------------------------------- execute decode
    logic [7:0]  typ;
    logic [15:0] seq, rg, dseq;
    logic [31:0] wval;
    logic        typ_ok, len_ok, seq_ok, rg_bad, accepted;
    logic [7:0]  need;
    logic [31:0] regval;
    logic [7:0]  status_c;
    logic [4:0]  plen_c;
    logic [135:0] pay_c;

    assign typ  = rbuf[0];
    assign seq  = {rbuf[2], rbuf[3]};
    assign rg   = {rbuf[4], rbuf[5]};
    assign wval = {rbuf[6], rbuf[7], rbuf[8], rbuf[9]};
    assign dseq = seq - last_seq;

    always_comb begin
        typ_ok = (typ >= 8'd1) && (typ <= 8'd5);
        case (typ)
            T_READ:   need = 8'd2;
            T_WRITE:  need = 8'd6;
            T_TSTART: need = 8'd2;
            default:  need = 8'd0;
        endcase
        len_ok = (ln == need);
        seq_ok = !have_last || ((dseq != 16'd0) && !dseq[15]);
        rg_bad = (rg >= 16'd8);
        accepted = typ_ok && len_ok && seq_ok;
        case (rg[2:0])
            3'd0:    regval = ID_WORD;
            3'd1:    regval = scratch1;
            3'd2:    regval = scratch2;
            3'd3:    regval = scratch3;
            3'd4:    regval = {16'h0000, cnt[0]};
            3'd5:    regval = {16'h0000, refused};
            3'd6:    regval = {16'h0000, period};
            default: regval = ticks;
        endcase
        status_c = 8'd0;
        plen_c   = 5'd0;
        pay_c    = '0;
        if (!typ_ok)       status_c = 8'd1;
        else if (!len_ok)  status_c = 8'd2;
        else if (!seq_ok)  status_c = 8'd4;
        else begin
            case (typ)
                T_READ: begin
                    if (rg_bad) status_c = 8'd3;
                    else begin
                        plen_c = 5'd4;
                        pay_c  = {regval, 104'h0};
                    end
                end
                T_WRITE: begin
                    if (rg_bad) status_c = 8'd3;
                    else if (rg[2:0] == 3'd0 || rg[2]) status_c = 8'd5;
                end
                T_STATUS: begin
                    plen_c = 5'd17;
                    pay_c  = {cnt[0], cnt[1], cnt[2], cnt[3], cnt[4], cnt[5], cnt[6],
                              fcount, 7'b0, tele_on};
                end
                default: ;
            endcase
        end
    end

    // ---------------------------------------------------------------- refusal strobes
    logic       ref_en, ok_en;
    logic [2:0] ref_idx;
    always_comb begin
        ref_en  = 1'b0;
        ok_en   = 1'b0;
        ref_idx = 3'd0;
        case (st)
            S_RX: if (to_fire) begin
                ref_en = 1'b1; ref_idx = 3'd2;
            end
            S_J: begin
                if (j_short1)      begin ref_en = 1'b1; ref_idx = 3'd2; end
                else if (j_long)   begin ref_en = 1'b1; ref_idx = 3'd3; end
                else if (j_short2) begin ref_en = 1'b1; ref_idx = 3'd2; end
            end
            S_CHK: if (crc != CRC_RESIDUE) begin
                ref_en = 1'b1; ref_idx = 3'd1;
            end
            S_EXEC: begin
                if (status_c != 8'd0) begin
                    ref_en = 1'b1;
                    if (status_c == 8'd4) ref_idx = (dseq == 16'd0) ? 3'd4 : 3'd5;
                    else                  ref_idx = 3'd6;
                end else begin
                    ok_en = 1'b1;
                end
            end
            default: ;
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 0; i < 7; i++) cnt[i] <= 16'h0000;
            refused <= 16'h0000;
        end else begin
            if (ref_en) begin
                cnt[ref_idx] <= cnt[ref_idx] + 16'd1;
                refused      <= refused + 16'd1;
            end
            if (ok_en) cnt[0] <= cnt[0] + 16'd1;
        end
    end

    assign led = cnt[0];

    // ---------------------------------------------------------------- reply builder
    logic        rg_we, rg_done;
    logic [4:0]  rg_idx;
    logic [7:0]  rg_data;
    logic [5:0]  rg_len;
    logic [31:0] rword, tword;

    frame_gen #(.PB(17)) u_rgen (
        .clk(clk), .rst(rst), .start(st == S_EXEC),
        .typ({1'b1, typ[6:0]}), .status(status_c), .seq(seq), .plen(plen_c),
        .payload(pay_c),
        .we(rg_we), .idx(rg_idx), .data(rg_data), .done(rg_done), .len(rg_len));

    word_buf u_rbuf (
        .clk(clk), .we(rg_we), .widx(rg_idx), .wdata(rg_data),
        .ridx(ridx), .len(rlen), .rword(rword));

    // ---------------------------------------------------------------- ticks and telemetry
    logic        tick, due, cap;
    logic [31:0] ticks_nx;
    logic [8:0]  pend_sum;
    logic        tg_we, tg_done;
    logic [4:0]  tg_idx;
    logic [7:0]  tg_data;
    logic [5:0]  tg_len;

    assign tick     = (pend != 8'd0);
    assign ticks_nx = ticks + 32'd1;
    assign due      = tele_on && tick && ({1'b0, tcnt} + 17'd1 >= {1'b0, period});
    assign cap      = due && !held;
    assign pend_sum = {1'b0, pend} - {8'b0, tick} + (tick_wr ? {1'b0, win_wdata[7:0]} : 9'd0);

    frame_gen #(.PB(8)) u_tgen (
        .clk(clk), .rst(rst), .start(cap),
        .typ(8'hC0), .status(8'h00), .seq(fseq), .plen(5'd8),
        .payload({ticks_nx, cnt[0], refused}),
        .we(tg_we), .idx(tg_idx), .data(tg_data), .done(tg_done), .len(tg_len));

    word_buf u_tbuf (
        .clk(clk), .we(tg_we), .widx(tg_idx), .wdata(tg_data),
        .ridx(tidx), .len(held ? 6'd17 : 6'd0), .rword(tword));

    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_ok;
    assign unused_ok = tg_done ^ (|tg_len);
    /* verilator lint_on UNUSEDSIGNAL */

    // ---------------------------------------------------------------- main control
    always_ff @(posedge clk) begin
        if (rst) begin
            st        <= S_RX;
            nb        <= 8'd0;
            idle      <= '0;
            rlen      <= 6'd0;
            scratch1  <= 32'h0;
            scratch2  <= 32'h0;
            scratch3  <= 32'h0;
            period    <= DEF_PERIOD;
            ticks     <= 32'h0;
            pend      <= 8'd0;
            tele_on   <= 1'b0;
            tcnt      <= 16'h0;
            held      <= 1'b0;
            fseq      <= 16'h0;
            fcount    <= 16'h0;
            have_last <= 1'b0;
            last_seq  <= 16'h0;
            ridx      <= 7'd0;
            tidx      <= 7'd0;
        end else begin
            // window writes
            if (ridx_wr) ridx <= win_wdata[6:0];
            if (tidx_wr) tidx <= win_wdata[6:0];

            // ticks
            pend <= (pend_sum > 9'd255) ? 8'd255 : pend_sum[7:0];
            if (tick) ticks <= ticks_nx;
            if (tele_on && tick) begin
                if (due) tcnt <= 16'h0;
                else     tcnt <= tcnt + 16'd1;
            end
            if (cap) begin
                held   <= 1'b1;
                fseq   <= fseq + 16'd1;
                fcount <= fcount + 16'd1;
            end
            if (take_wr) held <= 1'b0;

            // packet receive and processing
            case (st)
                S_RX: begin
                    if (in_wr) begin
                        if (nb != 8'hFF) nb <= nb + 8'd1;
                        idle <= '0;
                        if (win_wdata[8]) begin
                            st   <= S_J;
                            rlen <= 6'd0;
                        end
                    end else if (nb != 8'd0) begin
                        if (to_fire) begin
                            nb   <= 8'd0;
                            idle <= '0;
                            rlen <= 6'd0;
                        end else begin
                            idle <= idle + 1'b1;
                        end
                    end
                end
                S_J: begin
                    if (j_short1 || j_long || j_short2) begin
                        st <= S_RX;
                        nb <= 8'd0;
                    end else begin
                        st <= S_CRC;
                    end
                end
                S_CRC: begin
                    if ({3'b0, ci} + 8'd1 == nb) st <= S_CHK;
                end
                S_CHK: begin
                    if (crc != CRC_RESIDUE) begin
                        st <= S_RX;
                        nb <= 8'd0;
                    end else begin
                        st <= S_EXEC;
                    end
                end
                S_EXEC: begin
                    st <= S_WAIT;
                    if (accepted) begin
                        have_last <= 1'b1;
                        last_seq  <= seq;
                    end
                    if (status_c == 8'd0) begin
                        case (typ)
                            T_WRITE: begin
                                case (rg[1:0])
                                    2'd1:    scratch1 <= wval;
                                    2'd2:    scratch2 <= wval;
                                    default: scratch3 <= wval;
                                endcase
                            end
                            T_TSTART: begin
                                if (rg != 16'd0) period <= (rg < MIN_PERIOD) ? MIN_PERIOD : rg;
                                tele_on <= 1'b1;
                                tcnt    <= 16'h0;
                            end
                            T_TSTOP: begin
                                tele_on <= 1'b0;
                                held    <= 1'b0;
                            end
                            default: ;
                        endcase
                    end
                end
                S_WAIT: begin
                    if (rg_done) begin
                        rlen <= rg_len;
                        st   <= S_RX;
                        nb   <= 8'd0;
                    end
                end
                default: st <= S_RX;
            endcase
        end
    end

    // ---------------------------------------------------------------- read mux
    logic busy;
    assign busy = (nb != 8'd0) || (st != S_RX) || (pend != 8'd0);

    always_ff @(posedge clk) begin
        if (win_rd) begin
            case (win_addr)
                7'd2:    win_rdata <= {26'b0, rlen};
                7'd3:    win_rdata <= {25'b0, ridx};
                7'd4:    win_rdata <= rword;
                7'd5:    win_rdata <= held ? 32'd17 : 32'd0;
                7'd6:    win_rdata <= {25'b0, tidx};
                7'd7:    win_rdata <= tword;
                7'd9:    win_rdata <= {30'b0, busy, tele_on};
                default: win_rdata <= 32'h0;
            endcase
        end
    end
endmodule
