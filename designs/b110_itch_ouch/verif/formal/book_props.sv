// book_props.sv (brief 188): quantity invariants of book_core.sv, attached by bind (book_bind.sv); the RTL is not edited.
// Idea from Edwards 2026, ch 13 (a formal proof that found a quantity wrap): the properties Q1-Q6 and the induction are our own, written from scratch.
//
// Form: yosys-slang reads only clocked Boolean concurrent assertions, so each property is the Boolean form of the SVA written beside it (the same convention as designs/b96_kr260_10g/verif/formal/rm_gp_props.sv).

//   Q1  no level is ever written live with zero size                     SVA: @(posedge clk) (|lv_we && !sweep) |-> !(lv_wd[64] && lv_wd[31:0] == 0)
//   Q2  an add to a level never lowers its size (no wrap)                 SVA: @(posedge clk) (d3_v && d3_add && any_hit) |-> (lv_wd[31:0] >= sz_hit && lv_wd[31:0] >= d3_amt)
//   Q3  a size that would pass 2^32 - 1 is flagged inexact in that clock SVA: @(posedge clk) (d3_v && d3_add && any_hit && sz_sum[32]) |-> inx_set[d3_inst]
//   Q4  an order-table entry is never written live with zero remaining    SVA: @(posedge clk) (we2 && !sweep) |-> !(wd2[EW-1] && wd2[31:0] == 0)
//   Q5  a live level read from either ladder port never has zero size     SVA: @(posedge clk) !sweep |-> no read level has valid set and size 0  (the state invariant: reachable states only, so BMC from reset)
//   Q6  a reduce never raises an order's remaining size                   SVA: @(posedge clk) (b2_v && b2_op == OP_RED && hit2 && we2 && wd2[EW-1]) |-> (wd2[31:0] <= e2_rem)
//
// Brief 191: k-induction. The six properties alone are not inductive: Q1 reads a level's size and an order's remaining size out of memory, and an arbitrary starting state
// may hold a live entry of no size. Two strengthening invariants say what the reachable states look like; with them the induction step closes at depth 1 (record:
// results/191_trading_variants/formal_book.json, with an ablation of each invariant, which fails without it). A first draft had seven; five of them (the sweep counter's range, the pipeline being empty during the sweep, a
// non-zero add quantity, the entry read for B2 and the entry written back) proved to be unnecessary when removed one at a time (formal_book_draft_with_seven_invariants.json and the ablation record), so they were dropped.
//   N1  what the sweep has passed is zero (every ladder group below the sweep counter, every table entry below it)
//   N2  outside the sweep no live ladder level and no live order has zero size (the Q5 invariant over EVERY entry, not only the ones read this clock)
module book_props #(
    parameter int N_INST = 2,
    parameter int LEVELS = 4,
    parameter int ORD_AW = 2,
    parameter int EW     = 1 + 64 + $clog2(N_INST > 1 ? N_INST : 2) + 1 + 32 + 32
) (
    input logic clk,
    input logic rst,
    input logic sweep,
    input logic [LEVELS-1:0] lv_we,
    input logic [64:0] lv_wd,
    input logic d3_v, d3_add, any_hit,
    input logic [31:0] sz_hit, d3_amt,
    input logic [32:0] sz_sum,
    input logic [N_INST-1:0] inx_set,
    input logic [$clog2(N_INST > 1 ? N_INST : 2)-1:0] d3_inst,
    input logic we2,
    input logic [EW-1:0] wd2,
    input logic b2_v,
    input logic [2:0] b2_op,
    input logic hit2,
    input logic [31:0] e2_rem,
    input logic [64:0] rda [0:LEVELS-1],
    input logic [64:0] rdb [0:LEVELS-1],
    // state for the invariants
    input logic [ORD_AW:0] sw_cnt,
    input logic [LEVELS-1:0] fv_lv_zero_live, fv_lv_unswept,
    input logic fv_ord_zero_live, fv_ord_unswept
);
    // A1: the first clock is a reset (every register of book_core is defined by it; the table and ladders are cleared by the sweep that follows, 2^ORD_AW + 1 clocks).
    // `live` = a reset has taken effect (not the first clock) and the sweep is not running; Q1 to Q6 and N2 are stated from then on. N1 describes the sweep itself.
    logic init_q;
    initial init_q = 1'b1;
    always_ff @(posedge clk) init_q <= 1'b0;
    always_comb a1_reset_first: assume (!init_q || rst);
    logic live, defined;
    assign defined = !init_q;
    assign live = !init_q && !sweep;
    logic rd_ok;
    always_comb begin
        rd_ok = 1'b1;
        for (int l = 0; l < LEVELS; l++) begin
            if (rda[l][64] && rda[l][31:0] == 32'd0) rd_ok = 1'b0;
            if (rdb[l][64] && rdb[l][31:0] == 32'd0) rd_ok = 1'b0;
        end
    end
    always_comb begin
        q1_no_zero_level:      assert (!live || !(|lv_we) || !(lv_wd[64] && lv_wd[31:0] == 32'd0));
        q2_no_wrap:            assert (!live || !(d3_v && d3_add && any_hit) || (lv_wd[31:0] >= sz_hit && lv_wd[31:0] >= d3_amt));
        q3_saturation_flagged: assert (!live || !(d3_v && d3_add && any_hit && sz_sum[32]) || inx_set[d3_inst]);
        q4_no_zero_entry:      assert (!live || !we2 || !(wd2[EW-1] && wd2[31:0] == 32'd0));
        q6_reduce_lowers:      assert (!live || !(b2_v && b2_op == 3'd1 && hit2 && we2 && wd2[EW-1]) || (wd2[31:0] <= e2_rem));
        q5_levels_never_zero_live: assert (!live || rd_ok);
    end
    // the strengthening invariants
    always_comb begin
        n1_swept_is_zero:   assert (!defined || !sweep || (fv_lv_unswept == '0 && !fv_ord_unswept));
        n2_no_zero_live:    assert (!live || (fv_lv_zero_live == '0 && !fv_ord_zero_live));
    end
    // not vacuous: a saturation and a level that is live both happen
    always_comb begin
        c_saturates:  cover (live && d3_v && d3_add && any_hit && sz_sum[32]);
        c_live_level: cover (live && rdb[0][64]);
        // brief 143c: each assertion's antecedent (the state in which it could be broken), paired by name (NAME__ante)
        q1_no_zero_level__ante:      cover (live && |lv_we);
        q2_no_wrap__ante:            cover (live && d3_v && d3_add && any_hit);
        q3_saturation_flagged__ante: cover (live && d3_v && d3_add && any_hit && sz_sum[32]);
        q4_no_zero_entry__ante:      cover (live && we2);
        q6_reduce_lowers__ante:      cover (live && b2_v && b2_op == 3'd1 && hit2 && we2 && wd2[EW-1]);
        q5_levels_never_zero_live__ante: cover (live);
        n1_swept_is_zero__ante:      cover (defined && sweep);
        n2_no_zero_live__ante:       cover (live);
    end
endmodule
