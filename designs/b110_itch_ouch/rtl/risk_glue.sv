// risk_glue.sv: decision glue between the book and the order builder: pre-trade risk checks, kill switch, position, order queue (brief 110).
//
// REUSE: the rule is the one of trade64 (rtl of designs/b96_kr260_10g): a new sell order at or below `thr` (price not zero) is a candidate to buy
// the instrument at that price for `qty`. trade64 reads that rule from a Bench Feed frame; here it is read from the ITCH Add Order that book_core
// has just added (the "adapter" is book_core's candidate flag and update record). The decision interface towards the order path is the one of
// trade64 widened to the OUCH fields: fire (here `go`), instrument, price, quantity, order number.
// Not reused: trade64's own receive path (it parses Bench Feed Ethernet frames).
//
// RISK (a stub: each check is a comparison against a register, every rejection counted, the first failing check is the reason; order of checks):
//   arm (not armed) -> kill (kill switch register) -> gap (untrusted packet, or a sequence gap while halt_on_gap) -> stale (the instrument's book is
//   inexact) -> size (quantity zero, above max_qty, or at least 1,000,000 as OUCH requires; with NOTIONAL_MODE not 0 also: price times quantity above the
//   notional limit, counted as rej_size) -> position (sent quantity of the instrument plus this order above max_pos) -> band (the order price must be
//   at most `band` above the reference price, and a reference must exist: with cfg_ref_sw 0 the reference is the best bid of this path's own book, as in
//   brief 110; with cfg_ref_sw 1 it is the price software wrote (cfg_ref_px, loaded by ref_load) and it must be no older than cfg_ref_age clocks; an
//   order price that wrapped past 2^32 - 1 is refused as band) -> hold-off (see below).
// HOLD-OFF (brief 188, the idea of b58a's rule hold-off): after an order is accepted for an instrument, the next candidate of that instrument is refused
//   for cfg_holdoff clocks (0 = off); the refusal is counted as rej_busy (timing dependent, so not part of the untimed model's counters), and speculation
//   is not started while any instrument is in hold-off.
// NOTIONAL (brief 188): NOTIONAL_MODE 0 = no check; 1 = order price times quantity against cfg_max_notional (a 32 by 32 bit multiply in the verdict
//   clock); 2 = a table written by software: price bucket (order price >> cfg_nt_shift, at most 15) -> largest quantity, so the check is one table read and a
//   compare. Software fills entry i with the notional limit divided by the highest price of bucket i, rounded down, so the table never admits an order the
//   multiply would refuse; it can refuse an order the multiply would admit (a price below the top of its bucket).
// The position is the quantity SENT for the instrument since clr_pos, not a filled position: no OUCH response is processed in phase 1.
//
// TIMING: the verdict is formed when book_core's update record for the candidate arrives (T+7). With cfg_spec the order frame was started at T+2
// (word 0 out at T+3) as soon as the candidate was seen, when nothing is in the way (no earlier candidate in flight, frame idle, nothing queued);
// the verdict then commits it (frame continues) or aborts it. Without cfg_spec, or when something is in the way, the frame starts at the verdict.
// A candidate that passes while the frame is busy waits in a four entry queue; a full queue rejects it (rej_busy), which is timing dependent:
// the tests keep candidates further apart than a frame, as a real session does not need two orders within eight clocks.
module risk_glue #(
    parameter int N_INST = 4,
    parameter int NOTIONAL_MODE = 0      // 0 none, 1 multiply, 2 price-band table
) (
    input  logic                 clk,
    input  logic                 rst,
    input  logic                 clr_cnt,
    input  logic                 clr_pos,
    input  logic                 clr_ref,
    input  logic [N_INST*64-1:0] cfg_watch,
    input  logic                 cfg_arm, cfg_kill, cfg_spec,
    input  logic [31:0]          cfg_qty, cfg_max_qty, cfg_max_pos, cfg_band, cfg_px_off,
    input  logic [15:0]          cfg_holdoff,              // clocks an instrument stays refused after an accepted order (0 = off)
    input  logic                 cfg_ref_sw,               // 0 the band reference is this path's own best bid, 1 the software reference below
    input  logic [31:0]          cfg_ref_px, cfg_ref_age,  // the software reference price, and the largest age in clocks it may have at a verdict
    input  logic                 ref_load,                 // one clock: cfg_ref_px was (re)written, the age restarts at 0
    input  logic [63:0]          cfg_max_notional,         // NOTIONAL_MODE 1: largest price times quantity
    input  logic [4:0]           cfg_nt_shift,             // NOTIONAL_MODE 2: price bucket = price >> shift (at most 15)
    input  logic [16*32-1:0]     cfg_nt_tbl,               // NOTIONAL_MODE 2: largest quantity per bucket
    // from book_core
    input  logic                 spec_start,
    input  logic [$clog2(N_INST > 1 ? N_INST : 2)-1:0] spec_inst,
    input  logic [31:0]          spec_px,
    input  logic                 spec_fail,
    input  logic                 tu_v,
    input  logic [$clog2(N_INST > 1 ? N_INST : 2)-1:0] tu_inst,
    input  logic [31:0]          tu_cpx,
    input  logic                 tu_cand, tu_spec, tu_gapblk, tu_inx,
    input  logic [31:0]          nt_px,                    // brief 188: book_core's ladder-update price three clocks before tu_cpx (the notional check is computed on it, so it costs no clock)
    input  logic [N_INST*2*32-1:0] tob_px,
    input  logic [N_INST*2-1:0]    tob_ok,
    input  logic                 book_ready,
    output logic                 spec_allow,
    // to ouch_enter
    output logic                 go,
    output logic                 go_spec,
    output logic [63:0]          f_sym,
    output logic [31:0]          f_px,
    output logic [31:0]          f_qty,
    output logic [31:0]          f_ref,
    output logic                 commit,
    output logic                 abort,
    input  logic                 b_busy,
    input  logic                 b_late,
    output logic [13*32-1:0]     cnt          // cand fire rej_arm rej_kill rej_gap rej_stale rej_size rej_pos rej_band rej_busy abort late_abort spec
);
    localparam int IW = $clog2(N_INST > 1 ? N_INST : 2);
    logic [31:0] pos [0:N_INST-1];
    logic [31:0] next_ref;

    // order queue
    logic [IW+96-1:0] dq [0:3];
    logic [2:0]       dq_cnt;
    logic             dq_full, dq_empty;
    assign dq_full  = (dq_cnt == 3'd4);
    assign dq_empty = (dq_cnt == 3'd0);

    // software reference: its age in clocks since ref_load (saturating), compared once a clock so the verdict only reads a flag
    logic [31:0] ref_age_q;
    logic        ref_fresh_q;
    always_ff @(posedge clk) begin
        if (rst) begin ref_age_q <= 32'hFFFF_FFFF; ref_fresh_q <= 1'b0; end
        else begin
            // fresh_q in a clock = (age in that clock) <= cfg_ref_age; the all-ones age means "never loaded, or older than 2^32 - 1 clocks" and is never fresh
            if (ref_load) begin ref_age_q <= 32'd0; ref_fresh_q <= 1'b1; end
            else begin
                if (ref_age_q != 32'hFFFF_FFFF) ref_age_q <= ref_age_q + 32'd1;
                ref_fresh_q <= (ref_age_q != 32'hFFFF_FFFF) && (ref_age_q < cfg_ref_age);
            end
        end
    end

    // hold-off per instrument
    logic [15:0]         ho_cnt [0:N_INST-1];
    logic [N_INST-1:0]   ho_act;
    always_comb for (int i = 0; i < N_INST; i++) ho_act[i] = (ho_cnt[i] != 16'd0);
    assign spec_allow = cfg_spec && cfg_arm && !cfg_kill && !b_busy && dq_empty && book_ready && (ho_act == '0);

    // verdict
    logic        v_cand;
    logic [31:0] v_price;
    logic        px_carry;
    logic        ref_ok;
    logic [31:0] ref_px;
    logic [32:0] pos_sum, band_lim, price33;
    logic        nt_bad, held;
    // notional check, pipelined over the three clocks the book takes from ladder update (B3) to top-of-book record (T+4 to T+7), so it costs no clock and its result is
    // in hand with tu_*: stage 1 order price (nt_px plus the offset, as v_price), stage 2 multiply or table index, stage 3 compare or table read. (Computed in the verdict
    // clock itself the multiply missed 6.2061 ns by 2.27 ns and the table by 0.63 ns: results/188_trading_safety/notional_measurement.md.)
    logic [31:0] nt1_px;
    logic        nt_bad_w;
    logic [63:0] nt_pa, nt_pb;
    logic [3:0]  nt2_i;
    logic        nt3_bad;
    always_ff @(posedge clk) begin
        nt1_px <= nt_px + cfg_px_off;                 // a carry out is not kept: the verdict's own price33 carry refuses a wrapped price as band
        nt_pa <= {32'd0, nt1_px} * {32'd0, cfg_qty};
        nt_pb <= nt_pa;
        nt2_i <= (nt1_px >> cfg_nt_shift > 32'd15) ? 4'd15 : 4'((nt1_px >> cfg_nt_shift) & 32'd15);
        nt3_bad <= cfg_qty > cfg_nt_tbl[32 * nt2_i +: 32];
    end
    always_comb begin
        nt_bad_w = 1'b0;
        if (NOTIONAL_MODE == 1) nt_bad_w = nt_pb > cfg_max_notional;           // wraps of the price cannot matter: a carry is refused as band
        else if (NOTIONAL_MODE == 2) nt_bad_w = nt3_bad;
    end
    logic [2:0]  reason;                 // 0 pass, 1 arm, 2 kill, 3 gap, 4 stale, 5 size, 6 pos, 7 band
    logic        pass;
    always_comb begin
        v_cand   = tu_v && tu_cand;
        price33  = {1'b0, tu_cpx} + {1'b0, cfg_px_off};
        v_price  = price33[31:0];
        px_carry = price33[32];
        ref_ok   = cfg_ref_sw ? ref_fresh_q : tob_ok[2 * tu_inst];
        ref_px   = cfg_ref_sw ? cfg_ref_px : tob_px[64 * tu_inst +: 32];
        pos_sum  = {1'b0, pos[tu_inst]} + {1'b0, cfg_qty};
        band_lim = {1'b0, ref_px} + {1'b0, cfg_band};
        held     = ho_act[tu_inst];
        nt_bad   = 1'b0;
        nt_bad   = nt_bad_w;
        reason = 3'd0;
        if (!cfg_arm) reason = 3'd1;
        else if (cfg_kill) reason = 3'd2;
        else if (tu_gapblk) reason = 3'd3;
        else if (tu_inx) reason = 3'd4;
        else if (cfg_qty == 32'd0 || cfg_qty > cfg_max_qty || cfg_qty >= 32'd1000000 || nt_bad) reason = 3'd5;
        else if (pos_sum > {1'b0, cfg_max_pos}) reason = 3'd6;
        else if (!(ref_ok && !px_carry && ({1'b0, v_price} <= band_lim))) reason = 3'd7;
        pass = v_cand && (reason == 3'd0) && !held;
    end
    logic [IW+96-1:0] v_rec;
    assign v_rec = {tu_inst, v_price, cfg_qty, next_ref};

    logic [31:0] c_cand, c_fire, c_rarm, c_rkill, c_rgap, c_rstale, c_rsize, c_rpos, c_rband, c_rbusy, c_abort, c_late, c_spec;
    assign cnt = {c_spec, c_late, c_abort, c_rbusy, c_rband, c_rpos, c_rsize, c_rstale, c_rgap, c_rkill, c_rarm, c_fire, c_cand};

    logic pop;
    logic [IW+96-1:0] go_rec;
    always_comb begin
        go = 1'b0; go_spec = 1'b0; go_rec = '0; pop = 1'b0; commit = 1'b0; abort = 1'b0;
        if (spec_start) begin
            go = 1'b1; go_spec = 1'b1; go_rec = {spec_inst, spec_px + cfg_px_off, cfg_qty, next_ref};
        end else if (pass && !tu_spec && !b_busy && dq_empty) begin
            go = 1'b1; go_rec = v_rec;
        end else if (!b_busy && !dq_empty) begin
            go = 1'b1; pop = 1'b1; go_rec = dq[0];
        end
        if (pass && tu_spec) commit = 1'b1;
        if ((v_cand && !pass && tu_spec) || spec_fail) abort = 1'b1;
    end
    assign f_ref = go_rec[31:0];
    assign f_qty = go_rec[63:32];
    assign f_px  = go_rec[95:64];
    always_comb begin
        f_sym = '0;
        for (int i = 0; i < N_INST; i++) if (go_rec[96 +: IW] == IW'(i)) f_sym = cfg_watch[64*i +: 64];
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            next_ref <= 32'd1; dq_cnt <= '0;
            for (int i = 0; i < N_INST; i++) begin pos[i] <= '0; ho_cnt[i] <= '0; end
            for (int i = 0; i < 4; i++) dq[i] <= '0;
            c_cand <= '0; c_fire <= '0; c_rarm <= '0; c_rkill <= '0; c_rgap <= '0; c_rstale <= '0; c_rsize <= '0; c_rpos <= '0; c_rband <= '0;
            c_rbusy <= '0; c_abort <= '0; c_late <= '0; c_spec <= '0;
        end else begin
            if (spec_start) c_spec <= c_spec + 32'd1;
            if (b_late) c_late <= c_late + 32'd1;
            if (abort) c_abort <= c_abort + 32'd1;
            if (pop) begin
                dq[0] <= dq[1]; dq[1] <= dq[2]; dq[2] <= dq[3]; dq_cnt <= dq_cnt - 3'd1;
            end
            if (v_cand) begin
                c_cand <= c_cand + 32'd1;
                case (reason)
                    3'd1: c_rarm   <= c_rarm   + 32'd1;
                    3'd2: c_rkill  <= c_rkill  + 32'd1;
                    3'd3: c_rgap   <= c_rgap   + 32'd1;
                    3'd4: c_rstale <= c_rstale + 32'd1;
                    3'd5: c_rsize  <= c_rsize  + 32'd1;
                    3'd6: c_rpos   <= c_rpos   + 32'd1;
                    3'd7: c_rband  <= c_rband  + 32'd1;
                    default: ;
                endcase
            end
            for (int i = 0; i < N_INST; i++) if (ho_cnt[i] != 16'd0) ho_cnt[i] <= ho_cnt[i] - 16'd1;
            if (v_cand && reason == 3'd0 && held) c_rbusy <= c_rbusy + 32'd1;                // refused in hold-off
            if (pass) begin
                if (tu_spec || (!b_busy && dq_empty) || !dq_full) begin
                    c_fire <= c_fire + 32'd1;
                    pos[tu_inst] <= pos[tu_inst] + cfg_qty;
                    ho_cnt[tu_inst] <= cfg_holdoff;
                    next_ref <= next_ref + 32'd1;
                    if (!tu_spec && !(!b_busy && dq_empty)) begin
                        // queued behind a busy frame (the pop above and this push are not in the same clock: a push needs b_busy or a non-empty queue)
                        dq[pop ? dq_cnt[1:0] - 2'd1 : dq_cnt[1:0]] <= v_rec;
                        dq_cnt <= pop ? dq_cnt : dq_cnt + 3'd1;
                    end
                end else c_rbusy <= c_rbusy + 32'd1;
            end
            if (clr_cnt) begin
                c_cand <= '0; c_fire <= '0; c_rarm <= '0; c_rkill <= '0; c_rgap <= '0; c_rstale <= '0; c_rsize <= '0; c_rpos <= '0; c_rband <= '0;
                c_rbusy <= '0; c_abort <= '0; c_late <= '0; c_spec <= '0;
            end
            if (clr_pos) for (int i = 0; i < N_INST; i++) pos[i] <= '0;
            if (clr_ref) next_ref <= 32'd1;
        end
    end
endmodule
