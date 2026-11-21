// ml_stage.sv (brief 113): the ML decision stage of build rm_gp_ml, in the core clock (TXUSRCLK2).
//
// What it is. The one-instrument book, the order-flow feature unit of brief 87 (ml_feat.sv, same arithmetic, bit-exact to model/lobsim.py FeatureState) and the
// boosted-tree classifier gbt_comb (brief 87 arm (a), 30 trees, 3 classes), arranged so that the class for the NEXT message is ready before that message arrives.
// Every input of the model is the book (and the windows of past messages) as it stands BEFORE the message under decision (brief 93, stage 0: no input depends on the
// message's own price, size, type or side), so it is a function of registers that only change when a good frame ends. The class therefore comes from a feed-forward
// pipeline that runs continuously behind those registers (3 clocks), and the decision at the message's price word reads a ready class: no clock is added to the order path.
//
// State and update. State: the book of the tracked instrument (best bid and ask, price and size), the previous snapshot P, a 16-term order-flow window, an 8-term
// trade-sign window and the direction of the last mid change. A tracked message (the first message of a frame that the rule path accepts: addressed to us, feed port,
// Bench Feed header good, IPv4 length at most 60) is OBSERVED at its price word (obs_v: type, side, price, size are latched) and APPLIED only when its frame ends good
// (end_v with end_good: FCS good, no error character, the length equal to the IPv4 length plus 18, as the verdict of the order's own frame). A frame that ends bad
// changes nothing, so a corrupted or cut frame can never move the model's state. APPLY does what ml_feat's `go` did: P := book, the windows shift, the direction is
// updated, and the book takes the message (ADD and MODIFY set the side, CANCEL empties it, TRADE reduces it at its best price, as b58a_trigger/rtl/book.sv). Features
// and class are taken from the state before the application, the same pair as in 58A.
//
// Pipeline (clock C = the clock that applies): C+1 state visible; C+2 stage-1 registers (e, direction, sizes, spread, imbalance bucket, trade term); C+3 features
// registered (`feat_r`); C+4 class registered (gbt_comb). `settle` counts the C+1..C+3 clocks; `cls_ok` is 1 when it has run out. A decision before that point is
// counted (n_late) and, in veto mode, fails closed (no order). With frames at least 10 clocks apart it cannot happen; the counter proves it on hardware.
// Applying while the pipeline has not settled is counted too (n_race); the values applied would then be stale.
//
// Reset: `rst` (the transmit side not up) and `st_rst` (a pulse from the register block) clear the state and the counters; `clr` clears the counters only.
module ml_stage (
    input  logic        clk,
    input  logic        rst,
    input  logic        clr,
    input  logic        st_rst,
    input  logic [15:0] ml_inst,
    input  logic        en_veto,
    // observation (one clock, at the price word of a frame the rule path accepts)
    input  logic        obs_v,
    input  logic [15:0] obs_inst,
    input  logic [7:0]  obs_type,
    input  logic        obs_side,
    input  logic [31:0] obs_px, obs_sz,
    // a decision the rule wants to act on for the tracked instrument (same clock as obs_v)
    input  logic        dec_v,
    // end of every frame (one clock)
    input  logic        end_v,
    input  logic        end_good,
    // the class for the message now arriving
    output logic        agree,           // class is "up" and settled: a buy is allowed
    output logic [32 * ml_pkg::NMLW - 1:0] ml_vec
);
    localparam logic [7:0] T_TRADE = 8'd4;
    // ------------------------------------------------------------------ state
    logic [31:0]        bpx, bsz, apx, asz;            // the book of the tracked instrument
    logic [31:0]        p_bpx, p_bsz, p_apx, p_asz;    // previous snapshot P
    logic signed [7:0]  ofi_w [16];
    logic signed [11:0] ofi_sum;
    logic signed [1:0]  tr_w [8];
    logic signed [4:0]  tr_sum;
    logic signed [1:0]  pend_sign;
    logic [1:0]         last_dir;
    // ------------------------------------------------------------------ pending message
    logic        pv;
    logic [7:0]  pt;
    logic        ps;
    logic [31:0] ppx, psz;
    logic        trk;
    assign trk = (obs_inst == ml_inst);
    // ------------------------------------------------------------------ stage 1: from the state registers
    logic signed [34:0] e_raw;
    logic signed [7:0]  e_c;
    always_comb begin
        e_raw = '0;
        if (bpx >= p_bpx) e_raw = e_raw + $signed({3'b000, bsz});
        if (bpx <= p_bpx) e_raw = e_raw - $signed({3'b000, p_bsz});
        if (apx <= p_apx) e_raw = e_raw - $signed({3'b000, asz});
        if (apx >= p_apx) e_raw = e_raw + $signed({3'b000, p_asz});
        e_c = e_raw > 35'sd127 ? 8'sd127 : (e_raw < -35'sd127 ? -8'sd127 : 8'(e_raw));
    end
    logic [32:0] mid_p, mid_s;
    assign mid_p = {1'b0, p_bpx} + {1'b0, p_apx};
    assign mid_s = {1'b0, bpx} + {1'b0, apx};
    logic [1:0] dir_c;
    assign dir_c = mid_s > mid_p ? 2'd2 : (mid_s < mid_p ? 2'd0 : last_dir);
    logic [7:0]  fb_c, fa_c;
    logic [3:0]  fspr_c;
    logic [2:0]  fimb_c;
    logic [31:0] spr;
    assign fb_c = (bpx == 0) ? 8'd0 : (bsz > 32'd255 ? 8'd255 : bsz[7:0]);
    assign fa_c = (apx == 0) ? 8'd0 : (asz > 32'd255 ? 8'd255 : asz[7:0]);
    assign spr = apx - bpx;
    assign fspr_c = (bpx == 0 || apx == 0 || apx < bpx || spr > 32'd15) ? 4'd15 : spr[3:0];
    logic [10:0] b4, b3, b2, b1, a4, a3, a2, a1;
    assign b1 = {3'b0, fb_c}; assign b2 = b1 << 1; assign b3 = b1 + b2; assign b4 = b1 << 2;
    assign a1 = {3'b0, fa_c}; assign a2 = a1 << 1; assign a3 = a1 + a2; assign a4 = a1 << 2;
    assign fimb_c = 3'(b4 > a1) + 3'(b2 > a1) + 3'(b3 > a2) + 3'(b1 > a1) + 3'(b2 > a3) + 3'(b1 > a2) + 3'(b1 > a4);
    logic signed [4:0] tr_new_c;
    assign tr_new_c = tr_sum - 5'(tr_w[0]) + 5'(pend_sign);
    logic        s1_pm;                                    // the previous message was a trade: the window moves on the next application
    logic signed [7:0]  s1_e;
    logic [1:0]  s1_dir;
    logic [7:0]  s1_fb, s1_fa;
    logic [3:0]  s1_fspr;
    logic [2:0]  s1_fimb;
    logic signed [4:0]  s1_trn;
    logic [4:0]  s1_ftr;
    always_ff @(posedge clk) begin
        s1_e <= e_c; s1_dir <= dir_c; s1_fb <= fb_c; s1_fa <= fa_c; s1_fspr <= fspr_c; s1_fimb <= fimb_c;
        s1_trn <= tr_new_c; s1_pm <= (pend_sign != 0);
        s1_ftr <= (pend_sign != 0) ? 5'(tr_new_c + 5'sd8) : 5'(tr_sum + 5'sd8);
    end
    // ------------------------------------------------------------------ stage 2: features
    logic signed [11:0] s2_ofi_new;
    logic [37:0] feat_r;
    logic signed [11:0] ofi_new_c;
    logic [7:0]  fofi_c;
    assign ofi_new_c = ofi_sum - 12'(ofi_w[0]) + 12'(s1_e);
    assign fofi_c = ofi_new_c > 12'sd127 ? 8'd255 : (ofi_new_c < -12'sd127 ? 8'd1 : 8'(ofi_new_c + 12'sd128));
    always_ff @(posedge clk) begin
        s2_ofi_new <= ofi_new_c;
        feat_r <= {s1_dir, fofi_c, s1_ftr, s1_fimb, s1_fspr, s1_fa, s1_fb};
    end
    // ------------------------------------------------------------------ stage 3: the classifier (registered output)
    logic [1:0] cls;
    logic       cls_v_unused;
    gbt_comb u_gbt (.clk, .rst, .in_v(1'b1), .in_f(feat_r), .out_v(cls_v_unused), .out_cls(cls));
    logic [2:0] settle;
    logic       cls_ok;
    assign cls_ok = (settle == 3'd0);
    assign agree  = cls_ok && (cls == 2'd2);
    // ------------------------------------------------------------------ the application of a good frame's message
    logic        apply;
    assign apply = end_v && end_good && pv;
    // the book after the message (book.sv semantics)
    logic [31:0] nbpx, nbsz, napx, nasz, cpx, csz;
    always_comb begin
        nbpx = bpx; nbsz = bsz; napx = apx; nasz = asz;
        cpx = ps ? apx : bpx;
        csz = ps ? asz : bsz;
        case (pt)
            8'h01, 8'h02: begin cpx = ppx; csz = psz; end
            8'h03:        begin cpx = '0;  csz = '0; end
            8'h04:        if (cpx == ppx && csz != 0) begin
                              csz = (csz > psz) ? csz - psz : 32'd0;
                              if (csz == 0) cpx = '0;
                          end
            default: ;
        endcase
        if (pt >= 8'h01 && pt <= 8'h04) begin
            if (ps) begin napx = cpx; nasz = csz; end else begin nbpx = cpx; nbsz = csz; end
        end
    end
    logic [31:0] n_obs, n_cls0, n_cls1, n_cls2, n_dec, n_veto, n_would, n_late, n_apply, n_drop, n_race;
    logic [31:0] last_feat_lo;
    logic [5:0]  last_feat_hi;
    logic [1:0]  last_cls;
    always_ff @(posedge clk) begin
        if (rst || st_rst) begin
            bpx <= '0; bsz <= '0; apx <= '0; asz <= '0; p_bpx <= '0; p_bsz <= '0; p_apx <= '0; p_asz <= '0;
            for (int i = 0; i < 16; i++) ofi_w[i] <= '0;
            for (int i = 0; i < 8; i++) tr_w[i] <= '0;
            ofi_sum <= '0; tr_sum <= '0; pend_sign <= '0; last_dir <= 2'd1; pv <= 1'b0;
            settle <= 3'd3;
            n_obs <= '0; n_cls0 <= '0; n_cls1 <= '0; n_cls2 <= '0; n_dec <= '0; n_veto <= '0; n_would <= '0; n_late <= '0; n_apply <= '0; n_drop <= '0; n_race <= '0;
            last_feat_lo <= '0; last_feat_hi <= '0; last_cls <= 2'd1;
        end else begin
            if (settle != 3'd0) settle <= settle - 3'd1;
            if (obs_v && trk) begin
                pv <= 1'b1; pt <= obs_type; ps <= obs_side; ppx <= obs_px; psz <= obs_sz;
                n_obs <= n_obs + 32'd1;
                if (cls == 2'd0) n_cls0 <= n_cls0 + 32'd1;
                if (cls == 2'd1) n_cls1 <= n_cls1 + 32'd1;
                if (cls == 2'd2) n_cls2 <= n_cls2 + 32'd1;
                if (!cls_ok) n_late <= n_late + 32'd1;
                last_feat_lo <= feat_r[31:0]; last_feat_hi <= feat_r[37:32]; last_cls <= cls;
                if (dec_v) begin
                    n_dec <= n_dec + 32'd1;
                    if (!agree) begin
                        if (en_veto) n_veto <= n_veto + 32'd1; else n_would <= n_would + 32'd1;
                    end
                end
            end
            if (end_v) begin
                pv <= 1'b0;
                if (pv && !end_good) n_drop <= n_drop + 32'd1;
            end
            if (apply) begin
                n_apply <= n_apply + 32'd1;
                if (settle != 3'd0) n_race <= n_race + 32'd1;
                p_bpx <= bpx; p_bsz <= bsz; p_apx <= apx; p_asz <= asz;
                for (int i = 0; i < 15; i++) ofi_w[i] <= ofi_w[i + 1];
                ofi_w[15] <= s1_e;
                ofi_sum <= s2_ofi_new;
                if (s1_pm) begin
                    for (int i = 0; i < 7; i++) tr_w[i] <= tr_w[i + 1];
                    tr_w[7] <= pend_sign;
                    tr_sum <= s1_trn;
                end
                pend_sign <= (pt == T_TRADE) ? (ps ? 2'sd1 : -2'sd1) : 2'sd0;
                last_dir <= s1_dir;
                bpx <= nbpx; bsz <= nbsz; apx <= napx; asz <= nasz;
                settle <= 3'd3;
            end
            if (clr) begin
                n_obs <= '0; n_cls0 <= '0; n_cls1 <= '0; n_cls2 <= '0; n_dec <= '0; n_veto <= '0; n_would <= '0; n_late <= '0; n_apply <= '0; n_drop <= '0; n_race <= '0;
            end
        end
    end
    // ------------------------------------------------------------------ status words (docs/ml_registers.md)
    logic [31:0] mw [ml_pkg::NMLW];
    always_comb begin
        mw[0] = n_obs; mw[1] = n_cls0; mw[2] = n_cls1; mw[3] = n_cls2; mw[4] = n_dec; mw[5] = n_veto; mw[6] = n_would; mw[7] = n_late;
        mw[8] = n_apply; mw[9] = n_drop; mw[10] = n_race; mw[11] = last_feat_lo;
        mw[12] = {24'd0, last_cls, last_feat_hi};
        mw[13] = {bpx[7:0], bsz[7:0], apx[7:0], asz[7:0]};      // the low bytes of the book of the tracked instrument (a debug view)
    end
    always_comb for (int i = 0; i < ml_pkg::NMLW; i++) ml_vec[32 * i +: 32] = mw[i];
endmodule
