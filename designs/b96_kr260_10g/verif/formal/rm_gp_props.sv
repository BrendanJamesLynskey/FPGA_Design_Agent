// rm_gp_props.sv (brief 115): properties of rate_match_gp.sv, attached by bind (rm_gp_bind.sv); the RTL is not edited.
//
// Form. Yosys's free SystemVerilog front end (yosys-slang, OSS CAD Suite) reads only clocked Boolean concurrent assertions, `assert property (@(posedge clk) expr);`: no |->, |=>, ##, s_eventually.
// So each property is written twice: (1) the SVA text of the intended property, in a comment marked SVA:, which a commercial tool reads as it is, and (2) the same property compiled by hand
// into a Boolean assertion over a few monitor registers (what an SVA compiler builds from the operators). docs/formal_study_notes.md maps each one to LTL/CTL.
//
// Two clocks. Every register in the monitor belongs to exactly one clock; an assertion is clocked by the domain whose registers it reads most, and reads of the other domain's state are plain
// observations of the model's state at that instant (the proof is over interleavings of the two clock edges, see rm_gp_fv_top.sv).
// Checked at every step, not at a clock edge: an invariant clocked on one edge constrains an induction hypothesis only at steps where that clock rises, and with two free clocks there can be many steps with none.
`define FV_BOTH(NAME, EXPR) always_comb NAME: assert (EXPR);
module rm_gp_props #(
    parameter int AW = 2,
    parameter bit ENT_SYNC = 1'b1,               // rate_match_gp's ENT_SYNC (the pointer crosses with ENT_SYNC ? 3 : 2 flops; the entry copies exist only with 1)
    parameter int KB = 0                         // the bit of the 74-bit entry the symbolic-entry proof follows: 0..63 data, 64..71 control mask, 72 ordered-set flag, 73 pure-idle flag
) (
    input logic wclk, rclk, wrst, rrst,
    input logic w_v, w_os, w_lock,
    input logic [63:0] w_d,
    input logic [7:0]  w_c,
    input logic wr_en, f_full,
    input logic [73:0] w_ent,
    input logic [AW:0] wbin, rbin, rbin_w, wbin_r, fill,
    input logic can_read, lock_s, slot, in_frame, do_pop, do_del, rd_en,
    input logic [5:0] pace,
    input logic [73:0] head,
    input logic [73:0] ent [1 << AW],
    input logic r_v,
    input logic [63:0] r_d,
    input logic [7:0]  r_c
);
    localparam int DEPTH = 1 << AW;
    localparam int CW    = AW + 1;
    localparam logic [CW-1:0] MASK = '1;

    function automatic logic [CW-1:0] gray(input logic [CW-1:0] b);
        return b ^ (b >> 1);
    endfunction
    function automatic logic in_frm(input logic [7:0] c, input logic [63:0] d);   // the spec's own frame test (XGMII: data block, Start in lane 0, Start in lane 4)
        return (c == 8'h00) || (c == 8'h01 && d[7:0] == 8'hFB) || (c == 8'h1F && d[39:32] == 8'hFB);
    endfunction

    wire [CW-1:0] true_fill = (wbin - rbin) & MASK;          // blocks written and not yet released by the reader: the ground truth both domains approximate
    wire [CW-1:0] wview     = (wbin - rbin_w) & MASK;        // the writer's (old) idea of it
    wire [CW-1:0] lag_r     = (rbin - rbin_w) & MASK;        // how far the writer's view of the read pointer is behind the reader
    wire [CW-1:0] lag_w     = (wbin - wbin_r) & MASK;        // how far the reader's view of the write pointer is behind the writer

    // ------------------------------------------------------------------ the symbolic entry (abstraction): one write sequence number tp, chosen once by the solver and then frozen
    // tp is a register with no power-up value that only ever reloads itself: unconstrained at step 0 and constant afterwards (an anyconst; the attribute (* anyconst *) is not honoured on a plain
    // wire by the slang front end, it would be re-chosen every step).
    logic [CW-1:0] tp;
    always_ff @(posedge wclk) tp <= tp;
    // wclk side: remember bit KB of the first item whose pointer value is tp
    // Bit-slice abstraction: the datapath is bit-parallel (each bit has its own entry flop, its own synchroniser chain, and is selected by the same pointers), so integrity is proved for one bit position at a time
    // (KB is a parameter; run_formal.py runs the classes of bit and, once, all 74). The state that matters to the other bits is the pointer logic, which is shared and fully modelled.
    logic        tw = 1'b0;
    logic        tbit = 1'b0;
    always_ff @(posedge wclk)
        if (wr_en && wbin == tp && !tw) begin tw <= 1'b1; tbit <= w_ent[KB]; end
    // rclk side: the item has been consumed (popped, deleted or drained)
    logic        done = 1'b0;
    logic        chk_out = 1'b0;                                // the item was popped last read clock: its block must be on the registered output now
    logic        spec_in = 1'b0;                                // the spec's frame state of the output stream
    wire         consume_tp = rd_en && rbin == tp && !done;
    wire         ins_any = !rrst && lock_s && slot && !can_read;                // slot with nothing to read: insert (if not in a frame) or stall
    // an empty slot clock: the RTL then inserts an idle or stalls; the monitor does not trust its choice, it watches whether an output block appeared (r_v) one clock later
    logic ins_q = 1'b0, sp_q = 1'b0;
    always_ff @(posedge rclk) begin
        ins_q <= ins_any; sp_q <= spec_in;
        chk_out <= 1'b0;
        if (rrst || !lock_s) spec_in <= 1'b0;
        else if (slot && can_read) spec_in <= in_frm(head[71:64], head[63:0]);
        if (consume_tp) begin
            done <= 1'b1;
            chk_out <= do_pop;
        end
    end

    // The reader's state (pace, in_frame, idle_run) has no power-up value in the RTL: it relies on rrst being asserted once before use (rate_match.sv does the same). `armed` is set by the first read clock;
    // the assumption below makes that clock a reset, and read-side assertions are armed from then on. (ASSUMPTION A1, all tasks.)
    logic armed = 1'b0;
    always_ff @(posedge rclk) armed <= 1'b1;
    always_comb a1_reset_at_first_read_clock: assume (armed || rrst);

    // ASSUMPTION A2 (all tasks): the two clocks stay within a RATIO:1 band. rcnt counts read-clock edges, wcnt write-clock edges (each in its own domain); each domain also keeps a snapshot of the other's count taken at
    // its own edge, so rn = read edges since the last write edge and wn = write edges since the last read edge are exact at every step. The solver may not let either reach RATIO when its clock ticks:
    // between two edges of one clock there are at most RATIO edges of the other: any phase, any drift, any ratio inside the band, and both clocks tick infinitely often (the fairness the liveness form needs;
    // docs/formal_study_notes.md section 5). A simultaneous edge counts as "after".
`ifndef FV_RATIO
`define FV_RATIO 3
`endif
    localparam int RATIO = `FV_RATIO;
    logic [3:0] rcnt = '0, wcnt = '0, rsnap = '0, wsnap = '0;
    always_ff @(posedge rclk) rcnt <= rcnt + 4'd1;
    always_ff @(posedge wclk) wcnt <= wcnt + 4'd1;
    always_ff @(posedge wclk) rsnap <= rcnt;
    always_ff @(posedge rclk) wsnap <= wcnt;
    wire [3:0] rn = rcnt - rsnap;                              // read edges since the last write edge
    wire [3:0] wn = wcnt - wsnap;                              // write edges since the last read edge
    always_ff @(posedge rclk) a2r_ratio: assume (rn < 4'(RATIO));
    always_ff @(posedge wclk) a2w_ratio: assume (wn < 4'(RATIO));
`ifdef FV_PROGRESS
    // ASSUMPTION A3 (progress task only): the conditions under which progress is claimed: the PCS lock is high, the writer is not in reset, and the reader is reset exactly once (at its first clock).
    always_comb begin
        a3a_lock_high:   assume (w_lock);
        a3b_writer_live: assume (!wrst);
        a3c_reader_live: assume (!armed || !rrst);
    end
`endif

`ifndef FV_PROGRESS      // the progress task does not look at data: its problem is smaller without the data-side helpers
    // the entry copies' synchroniser state, one generate block per entry (downward hierarchical references from the bind site: g_ent[i].s.u_e.u)
    logic [1:0][73:0] u_data_s [1 << AW];
    logic [73:0]      u_data_h [1 << AW];
    if (ENT_SYNC) begin : g_dsrc
        for (genvar gi = 0; gi < (1 << AW); gi++) begin : e
            assign u_data_s[gi] = g_ent[gi].s.u_e.u.s;
            assign u_data_h[gi] = g_ent[gi].s.u_e.u.held;
        end
    end
`endif

    // ------------------------------------------------------------------ helper invariants (strengthening for k-induction; each is also an assertion, so the proof proves them)
    // Without them induction starts in states no run can reach. They are the invariant of the crossing, written down: (1) the tracker against the pointers, (2) the order of values in a pointer's synchroniser chain,
    // (3) the data copy of the tracked entry against the pointer's stage: a stage that shows the item as written implies a data stage that shows the right bit (the 3-flop pointer vs 2-flop data rule).
    // H1: before the item is written the write pointer has not reached it (pointers start at 0 and count up: no wrap before the first pass over tp).  SVA: !tw |-> wbin <= tp
    `FV_BOTH(h1_not_yet_written, tw || wbin <= tp)
    // H2: while the item is written and not consumed it lies inside the window of unread blocks.  SVA: (tw && !done) |-> 1 <= ((wbin - tp) & MASK) <= ((wbin - rbin) & MASK)
    wire [CW-1:0] age_q = (wbin - tp) & MASK;                  // position of the item from the newest block: 1 = the newest
    `FV_BOTH(h2_item_in_window, !(tw && !done) || (age_q >= CW'(1) && age_q <= true_fill))
    // H3: before the item is consumed the read pointer has not passed it.  SVA: !done |-> rbin <= tp
    `FV_BOTH(h3_reader_not_past, done || rbin <= tp)
`ifndef FV_PROGRESS
    // H4: the entry flop holds the written bit for as long as the item is unread.  SVA: (tw && !done) |-> ent[tp[AW-1:0]][KB] == written[KB]
    `FV_BOTH(h4_entry_holds, !(tw && !done) || ent[tp[AW-1:0]][KB] == tbit)
`endif
    // H8: before the item is written neither pointer has wrapped, so the read pointer is not ahead of the write pointer in plain numbers.  SVA: !tw |-> rbin <= wbin
    `FV_BOTH(h8_no_wrap_yet, tw || rbin <= wbin)
    // H3b: an item is consumed only after it was written, and the pending output check belongs to a consumed item.  SVA: done |-> tw      chk_out |-> done
    `FV_BOTH(h3b_done_implies_written, !done || tw)
    `FV_BOTH(h3c_check_implies_done, !chk_out || done)

    // H5: order in a pointer's synchroniser chain. Every stage holds an older value of the pointer than the stage before it, and the value never runs ahead:
    //     pdist(x) = (pointer - decode(x)) mod 2**CW is 0 or more and nondecreasing along  pointer, gray register, stage 0, stage 1, ...  (SVA: always pdist(g) <= pdist(s0) && pdist(s0) <= pdist(s1) ...)
    function automatic logic [CW-1:0] g2b(input logic [CW-1:0] g);
        logic [CW-1:0] b;
        for (int i = 0; i < CW; i++) b[i] = ^(g >> i);
        return b;
    endfunction
`ifndef FV_NW
`define FV_NW (ENT_SYNC ? 3 : 2)
`endif
    localparam int NW = `FV_NW;                                 // stages in the write pointer's chain: 3 with ENT_SYNC, 2 without
    wire [CW-1:0] wp_g = u_wp.g, wp_dl = u_wp.u.dlast;
    wire [NW-1:0][CW-1:0] wp_s = u_wp.u.s;
    wire [CW-1:0] rp_g = u_rp.g, rp_dl = u_rp.u.dlast;
    wire [1:0][CW-1:0] rp_s = u_rp.u.s;
    function automatic logic [CW-1:0] pdist(input logic [CW-1:0] ptr, input logic [CW-1:0] gx);
`ifdef FV_BIN_CROSSING
        return (ptr - gx) & MASK;
`else
        return (ptr - g2b(gx)) & MASK;
`endif
    endfunction
    wire [CW-1:0] dw_g = pdist(wbin, wp_g), dw_dl = pdist(wbin, wp_dl), dw_0 = pdist(wbin, wp_s[0]), dw_1 = pdist(wbin, wp_s[1]), dw_2 = pdist(wbin, wp_s[NW-1]);
    wire [CW-1:0] dr_g = pdist(rbin, rp_g), dr_dl = pdist(rbin, rp_dl), dr_0 = pdist(rbin, rp_s[0]), dr_1 = pdist(rbin, rp_s[1]);
    `FV_BOTH(h5a_wp_chain_order, dw_g <= CW'(1) && dw_g <= dw_dl && dw_dl <= dw_g + CW'(1) && dw_g <= dw_0 && dw_0 <= dw_1 && dw_1 <= dw_2 && dw_2 <= true_fill)
    `FV_BOTH(h5b_rp_chain_order, dr_g <= CW'(1) && dr_g <= dr_dl && dr_dl <= dr_g + CW'(1) && dr_g <= dr_0 && dr_0 <= dr_1 && dr_1 <= lag_r)

`ifndef FV_PROGRESS
    // H6: the tracked item against the write pointer's stages and the entry copy's stages.  P(x) = "stage x already shows the item as written" = pdist(x) < age_q.
    //     P(stage 0) -> the data copy's stage 0 holds the bit, or it was late (held) and is fixed next clock;  P(stage 1) -> data stage 0 holds the bit;  P(last stage) -> data stage 1 (the reader's copy) holds the bit.
    //     This is why the pointer needs one flop more than the data copy: without it P(stage 1) would arrive with the data still late.
    if (ENT_SYNC) begin : g_h6
        logic dc0, dc1, dh0;                                    // data copy of the tracked entry: stage 0 correct, stage 1 correct, stage 0 late
        always_comb begin
            dc0 = 1'b0; dc1 = 1'b0; dh0 = 1'b0;
            for (int i = 0; i < (1 << AW); i++)
                if (tp[AW-1:0] == AW'(i)) begin
                    dc0 = u_data_s[i][0][KB] == tbit; dc1 = u_data_s[i][1][KB] == tbit; dh0 = u_data_h[i][KB];
                end
        end
        wire act = tw && !done;
        `FV_BOTH(h6a_p0, !act || !(dw_0 < age_q) || dc0 || dh0)
        `FV_BOTH(h6b_p1, !act || !(dw_1 < age_q) || dc0)
        `FV_BOTH(h6c_p2, !act || !(dw_2 < age_q) || dc1)
    end
`endif

    // ------------------------------------------------------------------ safety, write side
    // P1 no overflow: the writer never writes into an entry the reader has not released.  SVA: wr_en |-> ((wbin - rbin) & MASK) < DEPTH
    p1_no_overflow: assert property (@(posedge wclk) !wr_en || true_fill < CW'(DEPTH));
    // P1b the buffer never holds more than DEPTH blocks.  SVA: always ((wbin - rbin) & MASK) <= DEPTH
    `FV_BOTH(p1b_bound, true_fill <= CW'(DEPTH))
    // P2 the writer's view of the read pointer is conservative (never ahead of the reader).  SVA: always lag_r <= wview
    `FV_BOTH(p2_wview, lag_r <= wview && wview <= CW'(DEPTH))
    // P3 the reader's view of the write pointer never runs ahead of the real one, and its fill is at most the true fill.  SVA: always lag_w <= true_fill  (and fill <= true_fill)
    `FV_BOTH(p3_rview, lag_w <= true_fill && fill <= true_fill)
    // P4 no underflow: a read, delete or drain only happens when a block has crossed and has been written.  SVA: rd_en |-> (fill != 0) && (true_fill != 0)
    `FV_BOTH(p4_no_underflow, !armed || !rd_en || (fill != '0 && true_fill != '0))
    // P5 gray pointers change by at most one bit per clock (both pointers).  SVA: $countones(gray(wbin) ^ gray($past(wbin))) <= 1
    logic [CW-1:0] wbin_q = '0, rbin_q = '0;
    always_ff @(posedge wclk) wbin_q <= wbin;
    always_ff @(posedge rclk) rbin_q <= rbin;
    `FV_BOTH(p5_gray_w, $countones(gray(wbin) ^ gray(wbin_q)) <= 1)
    `FV_BOTH(p5_gray_r, $countones(gray(rbin) ^ gray(rbin_q)) <= 1)

    // ------------------------------------------------------------------ safety, read side policy
    // P6 only between frames: an idle is inserted, and an idle deleted, only when the output stream is not inside a frame (spec_in is the spec's own tracking of the output stream).
    //    SVA: (empty slot clock && output block appears next clock) |-> !spec_in      and      do_del |-> !spec_in
    `FV_BOTH(p6a_insert_idle_only_between_frames, !(ins_q && r_v) || !sp_q)
    `FV_BOTH(p6b_delete_only_between_frames, !armed || !do_del || !spec_in)
    `FV_BOTH(p6c_spec_matches_rtl, !armed || in_frame == spec_in)
`ifndef FV_PROGRESS
    // P7 only pure idle blocks are deleted. Two parts. (a) At the write: the pure-idle flag (entry bit 73) is set only for the idle pattern, judged on the raw inputs.
    //    SVA: wr_en |-> (w_ent[73] |-> (w_c == 8'hFF && w_d == 64'h0707070707070707 && !w_os))
    p7a_flag_means_idle: assert property (@(posedge wclk) !wr_en || !w_ent[73] || (w_c == 8'hFF && w_d == 64'h0707070707070707 && !w_os));
    //    (b) At the read: the flag the reader sees for the item numbered tp is the flag that was written (P8a with KB = 73), and a deletion needs it (checked only in the KB = 73 slice).
    //    SVA: (do_del && rbin == tp && !done) |-> written_flag
    if (KB == 73) begin : g_p7b
        p7b_delete_only_flagged: assert property (@(posedge rclk) !armed || !(do_del && rbin == tp && !done) || (tw && tbit));
    end
    // P8 data integrity of the symbolic entry: the bit KB popped for write sequence number tp is the bit that was written, and (KB < 72) it is on the output one read clock later.
    //    SVA: (do_pop && rbin == tp && !done) |-> (head[KB] == written[KB]) ##1 (r_v && out[KB] == written[KB])
    p8a_pop_is_written_bit: assert property (@(posedge rclk) !armed || !(do_pop && rbin == tp && !done) || (tw && head[KB] == tbit));
    if (KB < 72) begin : g_p8b
        wire out_bit = (KB < 64) ? r_d[KB % 64] : r_c[KB % 8];
        `FV_BOTH(p8b_output_is_written_bit, !chk_out || (r_v && out_bit == tbit))   // a state invariant: chk_out and the output register are loaded by the same read-clock edge
    end
`endif
    // P9 no reading of an unwritten item (order): the item numbered tp is consumed only after it was written.  SVA: (rd_en && rbin == tp && !done) |-> tw
    p9_consume_after_write: assert property (@(posedge rclk) !armed || !consume_tp || tw);

    // ------------------------------------------------------------------ progress
    // P10 the written item is eventually consumed (popped, deleted or drained).
    //     SVA (liveness, linear time):  (tw && !done) |-> s_eventually done        needs fairness: both read and write clocks tick infinitely often, lock high, no reset: assumptions A2, A3.
    //     CTL reading:                  AG ((tw && !done) -> AF done)               "on every path" is what the fairness constraint on the paths restricts.
    //     SVA (bounded response):       (tw && !done) |-> ##[1:RMAX] done           a safety property: every violating trace is finite. This is what is proved.
    //     A ranking function turns the unbounded claim into three safety facts (the standard liveness-to-safety step; docs/formal_study_notes.md section 7):
    //       Rk = number of read clocks, counted worst case, until the item is consumed, from the state alone:
    //            Rk = vis + LK + (q + 1) + NS
    //            vis : read clocks until the pointer stage the reader uses shows the item as written (stage table below; if the write clock has not yet copied the pointer into its gray register, up to RATIO - rn more read clocks wait for that next write edge)
    //            LK  : read clocks until the lock reaches the reader (2-flop synchroniser, one late bit allowed)
    //            q   : blocks queued ahead of the item (each takes one slot clock to pop)
    //            NS  : 1 if the pace counter reaches its one non-slot clock (pace == 32) inside the window, else 0
    //       R1  Rk <= RMAX                                    (bounded)
    //       R2  while the item is unconsumed, every read clock lowers Rk by at least one  (a transition fact: checked against the Rk of the previous read clock)
    //       R1 and R2 and Rk >= 1 give: the item is consumed within RMAX read clocks of being written. Fairness enters through rn (A2): without it vis has no bound.
`ifdef FV_PROGRESS
    wire act_p = tw && !done;
    wire pg = dw_g < age_q, p0 = dw_0 < age_q, p1 = dw_1 < age_q, p2 = dw_2 < age_q;
    // the one gray bit that changes when the pointer steps over the item; it can show its old value for one read clock (a late bit) only if the item's step is the latest change and that bit is not already held
    wire [CW-1:0] ibit = gray(tp) ^ gray((tp + CW'(1)) & MASK);
    wire can_late = !(dw_dl < age_q) && ((u_wp.u.held & ibit) == '0);
    wire [5:0] vis = p2 ? 6'd0 : p1 ? 6'd1 : p0 ? 6'd2 : pg ? (can_late ? 6'd4 : 6'd3) : (6'(RATIO) - 6'(rn)) + 6'd4;
    wire lk1 = u_lk.u.s[1], lk0 = u_lk.u.s[0], lkh = u_lk.u.held;
    wire [5:0] lkw = lk1 ? 6'd0 : lk0 ? 6'd1 : lkh ? 6'd2 : 6'd3;
    wire [5:0] qa = 6'(true_fill - age_q);                       // blocks ahead of the item
    wire [5:0] other = vis + lkw + qa + 6'd1;
    wire [5:0] ns = (7'(pace) + 7'(other) >= 7'd32) ? 6'd1 : 6'd0;
    wire [5:0] rk = other + ns;
    localparam int RMAX = (RATIO + 4) + 3 + DEPTH + 1;
    logic [5:0] rk_q = '0;
    logic       act_q = 1'b0;
    always_ff @(posedge rclk) begin rk_q <= rk; act_q <= act_p && armed; end
    // H10: with the lock held high the lock chain fills from the front: a 1 never sits behind a 0.
    `FV_BOTH(h10_lock_chain_prefix, !lk1 || lk0)
    // H11: the previous-read-clock sample refers to an item that has been written.
    `FV_BOTH(h11_sample_implies_written, !act_q || tw)
    `FV_BOTH(h9_pace_range, !armed || pace <= 6'd32)
    `FV_BOTH(r1_rank_bounded, !armed || !act_p || rk <= 6'(RMAX))
    `FV_BOTH(r2_rank_decreases, !(act_q && act_p) || rk < rk_q)
`endif

    // ------------------------------------------------------------------ cover (the proofs are not vacuous)
    c_pop_tp:  cover property (@(posedge rclk) do_pop && rbin == tp && !done);
`ifdef FV_COVER_DEL     // the one non-slot clock in 33 needs about 70 steps of history: a separate, deeper cover job
    c_del_tp:  cover property (@(posedge rclk) do_del && rbin == tp && !done);
`endif
    c_ins:     cover property (@(posedge rclk) ins_any && !in_frame);
    c_full:    cover property (@(posedge wclk) f_full && w_v);
    c_wrap:    cover property (@(posedge rclk) done && rbin == tp);
    c_stall:   cover property (@(posedge rclk) ins_any && in_frame);
endmodule
