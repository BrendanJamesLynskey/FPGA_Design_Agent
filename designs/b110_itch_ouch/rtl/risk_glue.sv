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
//   inexact) -> size (quantity zero, above max_qty, or at least 1,000,000 as OUCH requires) -> position (sent quantity of the instrument plus this
//   order above max_pos) -> band (the order price must be at most `band` above the best bid, and a bid must exist).
// The position is the quantity SENT for the instrument since clr_pos, not a filled position: no OUCH response is processed in phase 1.
//
// TIMING: the verdict is formed when book_core's update record for the candidate arrives (T+7). With cfg_spec the order frame was started at T+2
// (word 0 out at T+3) as soon as the candidate was seen, when nothing is in the way (no earlier candidate in flight, frame idle, nothing queued);
// the verdict then commits it (frame continues) or aborts it. Without cfg_spec, or when something is in the way, the frame starts at the verdict.
// A candidate that passes while the frame is busy waits in a four entry queue; a full queue rejects it (rej_busy), which is timing dependent:
// the tests keep candidates further apart than a frame, as a real session does not need two orders within eight clocks.
module risk_glue #(
    parameter int N_INST = 4
) (
    input  logic                 clk,
    input  logic                 rst,
    input  logic                 clr_cnt,
    input  logic                 clr_pos,
    input  logic                 clr_ref,
    input  logic [N_INST*64-1:0] cfg_watch,
    input  logic                 cfg_arm, cfg_kill, cfg_spec,
    input  logic [31:0]          cfg_qty, cfg_max_qty, cfg_max_pos, cfg_band, cfg_px_off,
    // from book_core
    input  logic                 spec_start,
    input  logic [$clog2(N_INST > 1 ? N_INST : 2)-1:0] spec_inst,
    input  logic [31:0]          spec_px,
    input  logic                 spec_fail,
    input  logic                 tu_v,
    input  logic [$clog2(N_INST > 1 ? N_INST : 2)-1:0] tu_inst,
    input  logic [31:0]          tu_cpx,
    input  logic                 tu_cand, tu_spec, tu_gapblk, tu_inx,
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
    assign spec_allow = cfg_spec && cfg_arm && !cfg_kill && !b_busy && dq_empty && book_ready;

    // verdict
    logic        v_cand;
    logic [31:0] v_price;
    logic        bid_ok;
    logic [31:0] bid_px;
    logic [32:0] pos_sum, band_lim;
    logic [2:0]  reason;                 // 0 pass, 1 arm, 2 kill, 3 gap, 4 stale, 5 size, 6 pos, 7 band
    logic        pass;
    always_comb begin
        v_cand   = tu_v && tu_cand;
        v_price  = tu_cpx + cfg_px_off;
        bid_ok   = tob_ok[2 * tu_inst];
        bid_px   = tob_px[64 * tu_inst +: 32];
        pos_sum  = {1'b0, pos[tu_inst]} + {1'b0, cfg_qty};
        band_lim = {1'b0, bid_px} + {1'b0, cfg_band};
        reason = 3'd0;
        if (!cfg_arm) reason = 3'd1;
        else if (cfg_kill) reason = 3'd2;
        else if (tu_gapblk) reason = 3'd3;
        else if (tu_inx) reason = 3'd4;
        else if (cfg_qty == 32'd0 || cfg_qty > cfg_max_qty || cfg_qty >= 32'd1000000) reason = 3'd5;
        else if (pos_sum > {1'b0, cfg_max_pos}) reason = 3'd6;
        else if (!(bid_ok && ({1'b0, v_price} <= band_lim))) reason = 3'd7;
        pass = v_cand && (reason == 3'd0);
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
            for (int i = 0; i < N_INST; i++) pos[i] <= '0;
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
            if (pass) begin
                if (tu_spec || (!b_busy && dq_empty) || !dq_full) begin
                    c_fire <= c_fire + 32'd1;
                    pos[tu_inst] <= pos[tu_inst] + cfg_qty;
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
