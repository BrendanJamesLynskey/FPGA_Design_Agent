// book_core.sv: order-reference table and top-of-book for a small set of instruments (brief 110).
//
// WHAT IT IS: for N_INST instruments (found by the Stock Directory: a watched symbol's stock locate), every displayed order of the Add / Execute /
// Cancel / Delete / Replace messages is kept in an order table (ORD_N = 2^ORD_AW entries, direct-mapped on the low bits of the order reference),
// and per instrument and side the aggregate size per price level in a ladder of LEVELS levels. The top of book is the best level of the ladder.
// WHAT IT IS NOT: not a full-depth book (a side holds at most LEVELS distinct prices, a table index holds one live order), not every instrument
// (N_INST), no order priority. When either capacity is exceeded the event is counted (oovf, lvovf), the instrument is flagged inexact, and the book
// of that instrument is no longer trustworthy until clr_book. Nothing here fires an order; risk_glue does.
//
// PIPELINE (T = the clock in which the last byte of a message entered mold_rx):
//   T+2  the decoded event (itch_dec) = B1: stock-locate lookup, order-table read issue; a candidate (Add of a sell order at or below thr) may start
//        the order frame speculatively (spec_start)
//   T+3  B2: table entry in hand: hit / miss / duplicate / overflow, entry written back, size delta formed
//   T+4  B3: ladder level updated
//   T+5  T1: the ladder of the touched side read, eight levels reduced to two
//   T+6  T2: best level chosen
//   T+7  the top-of-book registers and the update record tu_* are visible (so the book update is 7 clocks after the last byte)
// Events may arrive on consecutive clocks; Replace takes two slots in B1, and a two-entry queue absorbs the clock this costs (it cannot overflow
// with real message lengths: three messages cannot end in three consecutive clocks since each is at least 14 bytes on the wire).
module book_core #(
    parameter int N_INST = 4,
    parameter int LEVELS = 8,
    parameter int ORD_AW = 8
) (
    input  logic                 clk,
    input  logic                 rst,
    input  logic                 clr_book,
    input  logic                 clr_cnt,
    input  logic [N_INST*64-1:0] cfg_watch,       // symbols, ASCII, first character in the top byte, space padded
    input  logic [31:0]          cfg_thr,         // candidate rule: new sell order at or below this price
    input  logic                 spec_allow,      // from risk_glue: speculation enabled, order frame idle, nothing queued
    input  logic                 gapblk_now,      // snapshot taken as each event is decoded: untrusted or (halt on gap and gap)
    // decoded event from itch_dec
    input  logic                 e_v,
    input  logic [2:0]           e_k,
    input  logic [15:0]          e_loc,
    input  logic [63:0]          e_ref,
    input  logic [63:0]          e_nref,
    input  logic                 e_sell,
    input  logic [31:0]          e_sh,
    input  logic [31:0]          e_px,
    input  logic [63:0]          e_stock,
    input  logic [7:0]           e_code,
    // speculative start of the order frame (one clock, with the candidate's fields)
    output logic                 spec_start,
    output logic [$clog2(N_INST > 1 ? N_INST : 2)-1:0] spec_inst,
    output logic [31:0]          spec_px,
    output logic                 spec_fail,       // a speculative candidate ended without a book update: cancel its frame
    // top-of-book update record (visible T+7)
    output logic                 tu_v,
    output logic [$clog2(N_INST > 1 ? N_INST : 2)-1:0] tu_inst,
    output logic                 tu_side,         // 0 bid, 1 ask
    output logic [31:0]          tu_px,           // best price of the touched side after the update
    output logic [31:0]          tu_sz,
    output logic                 tu_ok,           // the side is not empty
    output logic [31:0]          tu_cpx,          // price of the order that caused the update
    output logic                 tu_cand,         // the update is the Add of a candidate
    output logic                 tu_spec,         // ... whose frame was started speculatively
    output logic                 tu_gapblk,
    output logic                 tu_inx,          // the instrument was inexact when this update was made (this update included)
    output logic [31:0]          nt_px,           // brief 188: the price of the ladder update in stage B3, three clocks before tu_* (an early copy of tu_cpx, for risk_glue's pipelined notional check)
    // top of book registers, all instruments
    output logic [N_INST*2*32-1:0] tob_px,        // index inst*2 + side
    output logic [N_INST*2*32-1:0] tob_sz,
    output logic [N_INST*2-1:0]    tob_ok,
    output logic [N_INST-1:0]    inexact,
    output logic                 book_ready,      // the sweep after reset or clr_book is finished
    output logic [7:0]           sys_code,
    output logic [8*32-1:0]      cnt              // unwatch omiss odup oovf lvovf lvmiss oover evdrop
);
    // LEVELS is 4 or 8: the tree below reduces the levels in two compare steps
    localparam int IW  = $clog2(N_INST > 1 ? N_INST : 2);
    localparam int ORD_N = 1 << ORD_AW;
    localparam int NG  = N_INST * 2;
    localparam int GW  = IW + 1;
    localparam int LW  = $clog2(LEVELS > 1 ? LEVELS : 2);
    // order table entry: valid, ref, inst, side, px, rem
    localparam int EW = 1 + 64 + IW + 1 + 32 + 32;
    localparam logic [2:0] K_ADD = 3'd0, K_EXE = 3'd1, K_CAN = 3'd2, K_DEL = 3'd3, K_REP = 3'd4, K_DIR = 3'd5;
    localparam logic [2:0] OP_ADD = 3'd0, OP_RED = 3'd1, OP_DEL = 3'd2, OP_UDEL = 3'd3, OP_UADD = 3'd4;

    // ------------------------------------------------------------------ sweep (clears the table, the ladders and the maps)
    logic [ORD_AW:0] sw_cnt;
    logic            sweep;
    assign book_ready = !sweep;

    // ------------------------------------------------------------------ locate map (updated by Stock Directory messages, in message order)
    logic [15:0]       loc   [0:N_INST-1];
    logic [N_INST-1:0] loc_v;
    logic              in_watch;
    logic [IW-1:0]     in_inst;
    always_comb begin
        in_watch = 1'b0;
        in_inst  = '0;
        for (int i = N_INST - 1; i >= 0; i--) begin
            if (loc_v[i] && loc[i] == e_loc) begin in_watch = 1'b1; in_inst = IW'(i); end
        end
    end
    logic in_ord, in_take;
    assign in_ord  = e_v && (e_k == K_ADD || e_k == K_EXE || e_k == K_CAN || e_k == K_DEL || e_k == K_REP);
    assign in_take = in_ord && in_watch && !sweep;

    // ------------------------------------------------------------------ B1: queue, Replace second slot, bypass
    localparam int BW = 3 + IW + 1 + 64 + 64 + 32 + 32 + 1;     // kind inst sell ref nref sh px gapblk
    logic [BW-1:0] inb, q0, q1;
    assign inb = {e_k, in_inst, e_sell, e_ref, e_nref, e_sh, e_px, gapblk_now};
    logic [1:0] q_cnt;
    logic       u1_pend;
    logic [63:0] u1_nref;
    logic [31:0] u1_sh, u1_px;

    logic [BW-1:0] b1;
    logic          b1_v, b1_byp, b1_isu1;
    always_comb begin
        b1 = inb; b1_v = 1'b0; b1_byp = 1'b0; b1_isu1 = 1'b0;
        if (u1_pend) begin
            b1_v = 1'b1; b1_isu1 = 1'b1;
        end else if (q_cnt != 2'd0) begin
            b1 = q0; b1_v = 1'b1;
        end else if (in_take) begin
            b1_v = 1'b1; b1_byp = 1'b1;
        end
    end
    logic [2:0]    b1_k;
    logic [IW-1:0] b1_inst;
    logic          b1_sell, b1_gap;
    logic [63:0]   b1_ref, b1_nref;
    logic [31:0]   b1_sh, b1_px;
    assign {b1_k, b1_inst, b1_sell, b1_ref, b1_nref, b1_sh, b1_px, b1_gap} = b1;

    logic [2:0]    b1_op;
    logic [ORD_AW-1:0] b1_addr;
    logic [63:0]   b1_rref;
    logic [31:0]   b1_rsh, b1_rpx;
    always_comb begin
        b1_op = OP_ADD;
        case (b1_k)
            K_ADD: b1_op = OP_ADD;
            K_EXE, K_CAN: b1_op = OP_RED;
            K_DEL: b1_op = OP_DEL;
            default: b1_op = OP_UDEL;
        endcase
        b1_rref = b1_ref; b1_rsh = b1_sh; b1_rpx = b1_px;
        if (b1_isu1) begin
            b1_op = OP_UADD; b1_rref = u1_nref; b1_rsh = u1_sh; b1_rpx = u1_px;
        end
        b1_addr = b1_rref[ORD_AW-1:0];
    end

    // candidate rule (the rule of trade64: a new sell order at or below the threshold, price not zero)
    logic b1_cand;
    assign b1_cand = b1_v && !b1_isu1 && (b1_k == K_ADD) && b1_sell && (b1_px != 32'd0) && (b1_px <= cfg_thr);
    logic cand_ahead;                                      // defined below from the stage registers
    assign spec_start = b1_byp && b1_cand && spec_allow && !cand_ahead && book_ready;
    assign spec_inst  = b1_inst;
    assign spec_px    = b1_px;

    // ------------------------------------------------------------------ order table
    (* ram_style = "distributed" *) logic [EW-1:0] mem [0:ORD_N-1];
    logic [EW-1:0] rd_q;
    logic          wb_we;
    logic [ORD_AW-1:0] wb_addr;
    logic [EW-1:0] wb_data;
    logic          we2;
    logic [ORD_AW-1:0] a2;
    logic [EW-1:0] wd2;
    always_ff @(posedge clk) begin
        rd_q <= mem[b1_addr];
        if (sweep) mem[sw_cnt[ORD_AW-1:0]] <= '0;
        else if (we2) mem[a2] <= wd2;
    end

    // ------------------------------------------------------------------ B2 registers
    logic              b2_v, b2_cand, b2_spec, b2_gap;
    logic [2:0]        b2_op;
    logic [IW-1:0]     b2_inst;
    logic              b2_sell;
    logic [63:0]       b2_ref;
    logic [31:0]       b2_sh, b2_px;
    logic [ORD_AW-1:0] b2_addr;
    // Replace context from its first slot
    logic              ctx_v, ctx_side;
    logic [IW-1:0]     ctx_inst;

    // B3 (delta) registers
    logic              d3_v, d3_add, d3_cand, d3_spec, d3_gap;
    logic [IW-1:0]     d3_inst;
    logic              d3_side;
    logic [31:0]       d3_px, d3_amt;
    // T1 registers
    logic              t1_v, t1_side, t1_cand, t1_spec, t1_gap, t1_inx;
    logic [IW-1:0]     t1_inst;
    logic [31:0]       t1_cpx;
    // T2 registers
    logic              t2_v, t2_side, t2_cand, t2_spec, t2_gap, t2_inx;
    logic [IW-1:0]     t2_inst;
    logic [31:0]       t2_cpx;
    logic              t2a_v, t2b_v;
    logic [31:0]       t2a_px, t2a_sz, t2b_px, t2b_sz;

    assign nt_px = d3_px;
    assign cand_ahead = (b2_v && b2_cand) || (d3_v && d3_cand) || (t1_v && t1_cand) || (t2_v && t2_cand) || (tu_v && tu_cand);

    // forwarded table entry
    logic [EW-1:0] e2;
    logic          e2_v, e2_side, hit2;
    logic [63:0]   e2_ref;
    logic [IW-1:0] e2_inst;
    logic [31:0]   e2_px, e2_rem;
    always_comb begin
        e2 = (wb_we && wb_addr == b2_addr) ? wb_data : rd_q;
        {e2_v, e2_ref, e2_inst, e2_side, e2_px, e2_rem} = e2;
        hit2 = e2_v && (e2_ref == b2_ref);
    end

    // B2 decisions
    logic              n_odup, n_oovf, n_omiss, n_oover, set_inx2;
    logic              dl_v, dl_add, dl_side;
    logic [IW-1:0]     dl_inst;
    logic [31:0]       dl_px, dl_amt;
    logic              ctx_set;
    logic [IW-1:0]     add_inst;
    logic              add_side;
    always_comb begin
        we2 = 1'b0; a2 = b2_addr; wd2 = '0;
        n_odup = 1'b0; n_oovf = 1'b0; n_omiss = 1'b0; n_oover = 1'b0; set_inx2 = 1'b0;
        dl_v = 1'b0; dl_add = 1'b0; dl_side = 1'b0; dl_inst = '0; dl_px = '0; dl_amt = '0; ctx_set = 1'b0;
        add_inst = (b2_op == OP_UADD) ? ctx_inst : b2_inst;
        add_side = (b2_op == OP_UADD) ? ctx_side : b2_sell;
        if (b2_v) begin
            case (b2_op)
                OP_ADD, OP_UADD: begin
                    if (b2_op == OP_UADD && !ctx_v) begin
                        // the old order of a Replace was not found: nothing to add (the miss was counted in its first slot)
                    end else if (b2_sh == 32'd0) begin
                        // an Add of zero shares would be a live entry of no size: never entered (itch_dec already refuses it as m_bad); counted as oovf and the instrument is inexact
                        n_oovf = 1'b1; set_inx2 = 1'b1;
                    end else if (e2_v) begin
                        if (hit2) n_odup = 1'b1;
                        else begin n_oovf = 1'b1; set_inx2 = 1'b1; end
                    end else begin
                        we2 = 1'b1;
                        wd2 = {1'b1, b2_ref, add_inst, add_side, b2_px, b2_sh};
                        dl_v = 1'b1; dl_add = 1'b1; dl_inst = add_inst; dl_side = add_side; dl_px = b2_px; dl_amt = b2_sh;
                    end
                end
                OP_RED: begin
                    if (!hit2) n_omiss = 1'b1;
                    else begin
                        dl_v = 1'b1; dl_inst = e2_inst; dl_side = e2_side; dl_px = e2_px;
                        we2 = 1'b1;
                        if (b2_sh >= e2_rem) begin
                            n_oover = (b2_sh > e2_rem);
                            wd2 = '0; dl_amt = e2_rem;
                        end else begin
                            wd2 = {1'b1, e2_ref, e2_inst, e2_side, e2_px, e2_rem - b2_sh}; dl_amt = b2_sh;
                        end
                    end
                end
                default: begin     // OP_DEL, OP_UDEL
                    if (!hit2) n_omiss = 1'b1;
                    else begin
                        we2 = 1'b1; wd2 = '0;
                        dl_v = 1'b1; dl_inst = e2_inst; dl_side = e2_side; dl_px = e2_px; dl_amt = e2_rem;
                    end
                    ctx_set = (b2_op == OP_UDEL);
                end
            endcase
        end
    end
    assign spec_fail = b2_v && b2_spec && !(dl_v && dl_add);

    // ------------------------------------------------------------------ ladder: per level a small RAM indexed by group = {inst, side}
    logic [GW-1:0] ga, gb;
    assign ga = {d3_inst, d3_side};
    assign gb = {t1_inst, t1_side};
    logic [64:0]   rda [0:LEVELS-1];
    logic [64:0]   rdb [0:LEVELS-1];
    logic [LEVELS-1:0] lv_we;
    logic [64:0]   lv_wd;
    logic [GW-1:0] lv_wa;
    logic [LEVELS-1:0] hit_v, free_v;
    logic              any_hit, any_free, ovf3, miss3, sat3;
    logic [LW-1:0]     l_hit, l_free;
    logic [31:0]       sz_hit;
    logic [32:0]       sz_sum;                              // level size plus the added quantity, one bit wider: bit 32 is the carry (the level size would wrap)
    always_comb begin
        any_hit = 1'b0; any_free = 1'b0; l_hit = '0; l_free = '0; sz_hit = '0;
        for (int l = LEVELS - 1; l >= 0; l--) begin
            hit_v[l]  = rda[l][64] && (rda[l][63:32] == d3_px);
            free_v[l] = !rda[l][64];
            if (hit_v[l])  begin any_hit = 1'b1; l_hit = LW'(l); end
            if (free_v[l]) begin any_free = 1'b1; l_free = LW'(l); end
        end
        for (int l = 0; l < LEVELS; l++) if (hit_v[l]) sz_hit = sz_hit | rda[l][31:0];
        ovf3 = 1'b0; miss3 = 1'b0; sat3 = 1'b0;
        sz_sum = {1'b0, sz_hit} + {1'b0, d3_amt};
        lv_wd = '0; lv_wa = ga;
        lv_we = '0;
        if (d3_v) begin
            if (d3_add) begin
                if (any_hit) begin
                    // the level size saturates at 2^32 - 1 instead of wrapping; the instrument is then inexact (sat3 sets it, counted as lvovf)
                    lv_we[l_hit] = 1'b1; sat3 = sz_sum[32];
                    lv_wd = {1'b1, d3_px, sz_sum[32] ? 32'hFFFF_FFFF : sz_sum[31:0]};
                end
                else if (any_free) begin lv_we[l_free] = 1'b1; lv_wd = {1'b1, d3_px, d3_amt}; end
                else ovf3 = 1'b1;
            end else begin
                if (any_hit) begin
                    lv_we[l_hit] = 1'b1;
                    lv_wd = (d3_amt >= sz_hit) ? 65'd0 : {1'b1, d3_px, sz_hit - d3_amt};
                end else miss3 = 1'b1;
            end
        end
        if (sweep) begin lv_we = '1; lv_wd = '0; lv_wa = sw_cnt[GW-1:0]; end
    end
    generate
        for (genvar l = 0; l < LEVELS; l++) begin : g_lv
            logic [64:0] lm [0:NG-1];
            always_ff @(posedge clk) if (lv_we[l]) lm[lv_wa] <= lv_wd;
            assign rda[l] = lm[ga];
            assign rdb[l] = lm[gb];
        end
    endgenerate

    // ------------------------------------------------------------------ T1: eight levels to two; T2: best level
    function automatic logic better(input logic av, input logic [31:0] ap, input logic bv, input logic [31:0] bp, input logic ask);
        // 1 when a is at least as good as b (a wins ties)
        if (!av) better = 1'b0;
        else if (!bv) better = 1'b1;
        else better = ask ? (ap <= bp) : (ap >= bp);
    endfunction
    logic [64:0] c1 [0:LEVELS-1];
    logic        w1_v [0:LEVELS/2-1];
    logic [31:0] w1_p [0:LEVELS/2-1];
    logic [31:0] w1_s [0:LEVELS/2-1];
    logic        w2_v [0:1];
    logic [31:0] w2_p [0:1];
    logic [31:0] w2_s [0:1];
    always_comb begin
        for (int l = 0; l < LEVELS; l++) c1[l] = rdb[l];
        for (int j = 0; j < LEVELS / 2; j++) begin
            if (better(c1[2*j][64], c1[2*j][63:32], c1[2*j+1][64], c1[2*j+1][63:32], t1_side)) begin
                w1_v[j] = c1[2*j][64]; w1_p[j] = c1[2*j][63:32]; w1_s[j] = c1[2*j][31:0];
            end else begin
                w1_v[j] = c1[2*j+1][64]; w1_p[j] = c1[2*j+1][63:32]; w1_s[j] = c1[2*j+1][31:0];
            end
        end
        for (int j = 0; j < 2; j++) begin
            w2_v[j] = 1'b0; w2_p[j] = '0; w2_s[j] = '0;
            if (2 * j + 1 < LEVELS / 2) begin
                if (better(w1_v[2*j], w1_p[2*j], w1_v[2*j+1], w1_p[2*j+1], t1_side)) begin
                    w2_v[j] = w1_v[2*j]; w2_p[j] = w1_p[2*j]; w2_s[j] = w1_s[2*j];
                end else begin
                    w2_v[j] = w1_v[2*j+1]; w2_p[j] = w1_p[2*j+1]; w2_s[j] = w1_s[2*j+1];
                end
            end else if (2 * j < LEVELS / 2) begin
                w2_v[j] = w1_v[2*j]; w2_p[j] = w1_p[2*j]; w2_s[j] = w1_s[2*j];
            end
        end
    end
    logic fin_a;
    assign fin_a = better(t2a_v, t2a_px, t2b_v, t2b_px, t2_side);

    // ------------------------------------------------------------------ registers
    logic [31:0] c_unwatch, c_omiss, c_odup, c_oovf, c_lvovf, c_lvmiss, c_oover, c_evdrop;
    assign cnt = {c_evdrop, c_oover, c_lvmiss, c_lvovf, c_oovf, c_odup, c_omiss, c_unwatch};
    logic [31:0] r_tob_px [0:NG-1];
    logic [31:0] r_tob_sz [0:NG-1];
    logic [NG-1:0] r_tob_ok;
    always_comb begin
        for (int g = 0; g < NG; g++) begin
            tob_px[32*g +: 32] = r_tob_px[g];
            tob_sz[32*g +: 32] = r_tob_sz[g];
        end
    end
    assign tob_ok = r_tob_ok;

    logic [N_INST-1:0] inx_r;
    assign inexact = inx_r;
    logic [N_INST-1:0] inx_set;
    always_comb begin
        inx_set = '0;
        if (set_inx2) inx_set[add_inst] = 1'b1;
        if (ovf3 || sat3) inx_set[d3_inst] = 1'b1;
    end

    always_ff @(posedge clk) begin
        tu_v <= 1'b0;
        if (rst) begin
            sweep <= 1'b1; sw_cnt <= '0;
            loc_v <= '0; q_cnt <= '0; u1_pend <= 1'b0; b2_v <= 1'b0; d3_v <= 1'b0; t1_v <= 1'b0; t2_v <= 1'b0;
            ctx_v <= 1'b0; ctx_side <= 1'b0; ctx_inst <= '0; wb_we <= 1'b0; wb_addr <= '0; wb_data <= '0;
            inx_r <= '0; r_tob_ok <= '0; sys_code <= '0;
            c_unwatch <= '0; c_omiss <= '0; c_odup <= '0; c_oovf <= '0; c_lvovf <= '0; c_lvmiss <= '0; c_oover <= '0; c_evdrop <= '0;
            for (int g = 0; g < NG; g++) begin r_tob_px[g] <= '0; r_tob_sz[g] <= '0; end
            for (int i = 0; i < N_INST; i++) loc[i] <= '0;
            b2_cand <= 1'b0; b2_spec <= 1'b0; b2_gap <= 1'b0; b2_op <= '0; b2_inst <= '0; b2_sell <= 1'b0; b2_ref <= '0; b2_sh <= '0; b2_px <= '0; b2_addr <= '0;
            d3_add <= 1'b0; d3_cand <= 1'b0; d3_spec <= 1'b0; d3_gap <= 1'b0; d3_inst <= '0; d3_side <= 1'b0; d3_px <= '0; d3_amt <= '0;
            t1_side <= 1'b0; t1_cand <= 1'b0; t1_spec <= 1'b0; t1_gap <= 1'b0; t1_inx <= 1'b0; t1_inst <= '0; t1_cpx <= '0;
            t2_side <= 1'b0; t2_cand <= 1'b0; t2_spec <= 1'b0; t2_gap <= 1'b0; t2_inx <= 1'b0; t2_inst <= '0; t2_cpx <= '0;
            t2a_v <= 1'b0; t2b_v <= 1'b0; t2a_px <= '0; t2a_sz <= '0; t2b_px <= '0; t2b_sz <= '0;
            u1_nref <= '0; u1_sh <= '0; u1_px <= '0;
            q0 <= '0; q1 <= '0;
            tu_inst <= '0; tu_side <= 1'b0; tu_px <= '0; tu_sz <= '0; tu_ok <= 1'b0; tu_cpx <= '0; tu_cand <= 1'b0; tu_spec <= 1'b0; tu_gapblk <= 1'b0; tu_inx <= 1'b0;
        end else begin
            // ---- sweep
            if (sweep) begin
                sw_cnt <= sw_cnt + 1'b1;
                if (sw_cnt == (ORD_AW + 1)'(ORD_N - 1)) sweep <= 1'b0;
            end
            if (clr_book) begin
                sweep <= 1'b1; sw_cnt <= '0; loc_v <= '0; inx_r <= '0; r_tob_ok <= '0; ctx_v <= 1'b0;
                q_cnt <= '0; u1_pend <= 1'b0; b2_v <= 1'b0; d3_v <= 1'b0; t1_v <= 1'b0; t2_v <= 1'b0; wb_we <= 1'b0;
                for (int g = 0; g < NG; g++) begin r_tob_px[g] <= '0; r_tob_sz[g] <= '0; end
            end else begin
                // ---- stock directory and system events (in message order, at the decoded-event stage)
                if (e_v && !sweep) begin
                    if (e_k == K_DIR) begin
                        for (int i = 0; i < N_INST; i++) begin
                            if (e_stock == cfg_watch[64*i +: 64]) begin loc[i] <= e_loc; loc_v[i] <= 1'b1; end
                        end
                    end
                    if (e_k == 3'd6) sys_code <= e_code;
                end
                if (e_v && sweep) c_evdrop <= c_evdrop + 32'd1;
                if (in_ord && !sweep && !in_watch) c_unwatch <= c_unwatch + 32'd1;
                // ---- queue and Replace second slot
                if (u1_pend) begin
                    u1_pend <= 1'b0;
                    if (in_take) begin
                        if (q_cnt == 2'd0) begin q0 <= inb; q_cnt <= 2'd1; end
                        else if (q_cnt == 2'd1) begin q1 <= inb; q_cnt <= 2'd2; end
                        else c_evdrop <= c_evdrop + 32'd1;
                    end
                end else if (q_cnt != 2'd0) begin
                    // the head is taken by B1 this clock
                    if (in_take) begin
                        if (q_cnt == 2'd1) begin q0 <= inb; q_cnt <= 2'd1; end
                        else begin q0 <= q1; q1 <= inb; q_cnt <= 2'd2; end
                    end else begin
                        q0 <= q1; q_cnt <= q_cnt - 2'd1;
                    end
                    if (b1_k == K_REP) begin
                        u1_pend <= 1'b1; u1_nref <= b1_nref; u1_sh <= b1_sh; u1_px <= b1_px;
                    end
                end else if (in_take && b1_k == K_REP) begin
                    u1_pend <= 1'b1; u1_nref <= b1_nref; u1_sh <= b1_sh; u1_px <= b1_px;
                end
                // ---- B1 -> B2
                b2_v <= b1_v;
                b2_cand <= b1_cand; b2_spec <= spec_start; b2_gap <= b1_gap;
                b2_op <= b1_op; b2_inst <= b1_inst; b2_sell <= b1_sell; b2_ref <= b1_rref; b2_sh <= b1_rsh; b2_px <= b1_rpx; b2_addr <= b1_addr;
                // ---- B2: write back, context, delta
                wb_we <= we2; wb_addr <= a2; wb_data <= wd2;
                if (b2_v && ctx_set) begin ctx_v <= hit2; ctx_inst <= e2_inst; ctx_side <= e2_side; end
                if (n_odup)  c_odup  <= c_odup  + 32'd1;
                if (n_oovf)  c_oovf  <= c_oovf  + 32'd1;
                if (n_omiss) c_omiss <= c_omiss + 32'd1;
                if (n_oover) c_oover <= c_oover + 32'd1;
                d3_v <= dl_v; d3_add <= dl_add; d3_inst <= dl_inst; d3_side <= dl_side; d3_px <= dl_px; d3_amt <= dl_amt;
                d3_cand <= b2_cand && b2_op == OP_ADD && dl_v && dl_add; d3_spec <= b2_spec && dl_v && dl_add; d3_gap <= b2_gap;
                // ---- B3: ladder updated above (generate); counters; inexact flags
                if (ovf3 || sat3) c_lvovf <= c_lvovf + 32'd1;
                if (miss3) c_lvmiss <= c_lvmiss + 32'd1;
                for (int i = 0; i < N_INST; i++) if (inx_set[i]) inx_r[i] <= 1'b1;
                t1_v <= d3_v; t1_side <= d3_side; t1_inst <= d3_inst; t1_cand <= d3_cand; t1_spec <= d3_spec; t1_gap <= d3_gap;
                t1_cpx <= d3_px; t1_inx <= inx_r[d3_inst] | ovf3 | sat3;
                // ---- T1 -> T2
                t2_v <= t1_v; t2_side <= t1_side; t2_inst <= t1_inst; t2_cand <= t1_cand; t2_spec <= t1_spec; t2_gap <= t1_gap;
                t2_cpx <= t1_cpx; t2_inx <= t1_inx;
                t2a_v <= w2_v[0]; t2a_px <= w2_p[0]; t2a_sz <= w2_s[0];
                t2b_v <= w2_v[1]; t2b_px <= w2_p[1]; t2b_sz <= w2_s[1];
                // ---- T2: best level, top-of-book registers and update record
                if (t2_v) begin
                    tu_v <= 1'b1; tu_inst <= t2_inst; tu_side <= t2_side; tu_cpx <= t2_cpx; tu_cand <= t2_cand; tu_spec <= t2_spec;
                    tu_gapblk <= t2_gap; tu_inx <= t2_inx;
                    if (fin_a) begin
                        tu_px <= t2a_px; tu_sz <= t2a_sz; tu_ok <= t2a_v;
                        r_tob_px[{t2_inst, t2_side}] <= t2a_px; r_tob_sz[{t2_inst, t2_side}] <= t2a_sz; r_tob_ok[{t2_inst, t2_side}] <= t2a_v;
                    end else begin
                        tu_px <= t2b_px; tu_sz <= t2b_sz; tu_ok <= t2b_v;
                        r_tob_px[{t2_inst, t2_side}] <= t2b_px; r_tob_sz[{t2_inst, t2_side}] <= t2b_sz; r_tob_ok[{t2_inst, t2_side}] <= t2b_v;
                    end
                end
            end
            if (clr_cnt) begin
                c_unwatch <= '0; c_omiss <= '0; c_odup <= '0; c_oovf <= '0; c_lvovf <= '0; c_lvmiss <= '0; c_oover <= '0; c_evdrop <= '0;
            end
        end
    end
`ifdef FORMAL_BOOK
    // ------------------------------------------------------------------ formal only (brief 191): whole-memory views for the k-induction invariants in verif/formal/book_props.sv.
    // Not defined in any build; the memories themselves are not changed.
    logic [LEVELS-1:0] fv_lv_zero_live, fv_lv_unswept;
    for (genvar l = 0; l < LEVELS; l++) begin : g_fv
        always_comb begin
            fv_lv_zero_live[l] = 1'b0; fv_lv_unswept[l] = 1'b0;
            for (int g = 0; g < NG; g++) begin
                if (g_lv[l].lm[g][64] && g_lv[l].lm[g][31:0] == 32'd0) fv_lv_zero_live[l] = 1'b1;       // a live level of no size
                if ((ORD_AW + 1)'(g) < sw_cnt && g_lv[l].lm[g] != '0) fv_lv_unswept[l] = 1'b1;           // a group the sweep has passed that is not zero
            end
        end
    end
    logic fv_ord_zero_live, fv_ord_unswept;
    always_comb begin
        fv_ord_zero_live = 1'b0; fv_ord_unswept = 1'b0;
        for (int i = 0; i < ORD_N; i++) begin
            if (mem[i][EW-1] && mem[i][31:0] == 32'd0) fv_ord_zero_live = 1'b1;                         // a live order of no remaining size
            if ((ORD_AW + 1)'(i) < sw_cnt && mem[i] != '0) fv_ord_unswept = 1'b1;
        end
    end
`endif
endmodule
