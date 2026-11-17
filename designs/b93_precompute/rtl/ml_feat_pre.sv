// ml_feat_pre.sv: the 87 feature unit (ml_feat.sv), computed EARLY: as soon as the message's instrument field has been
// parsed and the book entry read (the clock after msg_inst_v), not when the price field completes.
//
// Why this is allowed: every input of the 87 features is known before the price field. The features are functions of
// the book entry read for this message (the book BEFORE the message), of the previous snapshot P, of the order-flow and
// trade windows and of the previous message's trade sign; the message's own price, size, type and side are not inputs
// (type and side only set the trade sign that the NEXT message uses). So the whole feature vector can be computed in
// the 3 clocks between the book read and the end of the price field.
//
// Timing, relative to the clock c of msg_inst_v: the book entry is on bk_* at c+1; this unit registers the feature
// vector at c+2 (feat_v/feat, one clock after trk_v); msg_px_v is at c+4.
//
// State is committed ONLY at msg_px_v, from values registered at the early clock, exactly where ml_feat.sv commits. A
// message that never reaches its price field (a cut-off frame) therefore leaves the state untouched, as in ml_feat.sv.
// Same function as ml_feat.sv at every message that reaches its price field: model/lobsim.py FeatureState is the twin.
// The packed feature layout and the empty-side convention are ml_feat.sv's.

module ml_feat_pre (
    input  logic        clk,
    input  logic        rst,
    input  logic [15:0] ml_inst,
    input  logic        inst_v,        // msg_inst_v: the instrument field has just completed
    input  logic        msg_px_v,
    input  logic [7:0]  msg_type,      // valid with msg_px_v
    input  logic        msg_side,      // valid with msg_px_v
    input  logic [15:0] msg_inst,      // valid from the clock after inst_v until the next message
    input  logic        bk_valid,
    input  logic [31:0] bk_bid_px, bk_bid_sz, bk_ask_px, bk_ask_sz,
    output logic        trk_v,         // a tracked message's features are being computed (c+1), registered at c+2
    output logic        feat_v,
    output logic [37:0] feat
);
    localparam logic [7:0] TRADE = 8'd4;
    logic inst_d;
    always_ff @(posedge clk) inst_d <= inst_v && !rst;
    logic pre;
    assign pre = inst_d && bk_valid && msg_inst == ml_inst;
    assign trk_v = pre;

    // committed state (as ml_feat.sv)
    logic [31:0]        p_bpx, p_bsz, p_apx, p_asz;
    logic signed [7:0]  ofi_w [16];
    logic signed [11:0] ofi_sum;
    logic signed [1:0]  tr_w [8];
    logic signed [4:0]  tr_sum;
    logic signed [1:0]  pend_sign;
    logic [1:0]         last_dir;

    logic signed [34:0] e_raw;
    logic signed [7:0]  e;
    always_comb begin
        e_raw = '0;
        if (bk_bid_px >= p_bpx) e_raw = e_raw + $signed({3'b000, bk_bid_sz});
        if (bk_bid_px <= p_bpx) e_raw = e_raw - $signed({3'b000, p_bsz});
        if (bk_ask_px <= p_apx) e_raw = e_raw - $signed({3'b000, bk_ask_sz});
        if (bk_ask_px >= p_apx) e_raw = e_raw + $signed({3'b000, p_asz});
        e = e_raw > 35'sd127 ? 8'sd127 : (e_raw < -35'sd127 ? -8'sd127 : 8'(e_raw));
    end
    logic signed [11:0] ofi_new;
    logic signed [4:0]  tr_new;
    assign ofi_new = ofi_sum - 12'(ofi_w[0]) + 12'(e);
    assign tr_new  = tr_sum - 5'(tr_w[0]) + 5'(pend_sign);

    logic [32:0] mid_p, mid_s;
    assign mid_p = {1'b0, p_bpx} + {1'b0, p_apx};
    assign mid_s = {1'b0, bk_bid_px} + {1'b0, bk_ask_px};
    logic [1:0] dir_new;
    assign dir_new = mid_s > mid_p ? 2'd2 : (mid_s < mid_p ? 2'd0 : last_dir);

    logic [7:0]  fb, fa, fofi;
    logic [3:0]  fspr;
    logic [2:0]  fimb;
    logic [4:0]  ftr;
    logic [31:0] spr;
    assign fb = (bk_bid_px == 0) ? 8'd0 : (bk_bid_sz > 32'd255 ? 8'd255 : bk_bid_sz[7:0]);
    assign fa = (bk_ask_px == 0) ? 8'd0 : (bk_ask_sz > 32'd255 ? 8'd255 : bk_ask_sz[7:0]);
    assign spr = bk_ask_px - bk_bid_px;
    assign fspr = (bk_bid_px == 0 || bk_ask_px == 0 || bk_ask_px < bk_bid_px || spr > 32'd15) ? 4'd15 : spr[3:0];
    logic [10:0] b4, b3, b2, b1, a4, a3, a2, a1;
    assign b1 = {3'b0, fb}; assign b2 = b1 << 1; assign b3 = b1 + b2; assign b4 = b1 << 2;
    assign a1 = {3'b0, fa}; assign a2 = a1 << 1; assign a3 = a1 + a2; assign a4 = a1 << 2;
    assign fimb = 3'(b4 > a1) + 3'(b2 > a1) + 3'(b3 > a2) + 3'(b1 > a1) + 3'(b2 > a3) + 3'(b1 > a2) + 3'(b1 > a4);
    assign ftr  = (pend_sign != 0) ? 5'(tr_new + 5'sd8) : 5'(tr_sum + 5'sd8);
    assign fofi = ofi_new > 12'sd127 ? 8'd255 : (ofi_new < -12'sd127 ? 8'd1 : 8'(ofi_new + 12'sd128));

    // registered at the early clock, committed at msg_px_v
    logic               pre_ok;
    logic [31:0]        c_bpx, c_bsz, c_apx, c_asz;
    logic signed [7:0]  c_e;
    logic signed [11:0] c_ofi;
    logic signed [4:0]  c_tr;
    logic [1:0]         c_dir;

    always_ff @(posedge clk) begin
        if (rst) begin
            p_bpx <= '0; p_bsz <= '0; p_apx <= '0; p_asz <= '0;
            for (int i = 0; i < 16; i++) ofi_w[i] <= '0;
            for (int i = 0; i < 8; i++) tr_w[i] <= '0;
            ofi_sum <= '0; tr_sum <= '0; pend_sign <= '0; last_dir <= 2'd1;
            feat_v <= 1'b0; pre_ok <= 1'b0;
        end else begin
            feat_v <= pre;
            if (msg_px_v && pre_ok) begin
                p_bpx <= c_bpx; p_bsz <= c_bsz; p_apx <= c_apx; p_asz <= c_asz;
                for (int i = 0; i < 15; i++) ofi_w[i] <= ofi_w[i + 1];
                ofi_w[15] <= c_e;
                ofi_sum <= c_ofi;
                if (pend_sign != 0) begin
                    for (int i = 0; i < 7; i++) tr_w[i] <= tr_w[i + 1];
                    tr_w[7] <= pend_sign;
                    tr_sum <= c_tr;
                end
                pend_sign <= (msg_type == TRADE) ? (msg_side ? 2'sd1 : -2'sd1) : 2'sd0;
                last_dir <= c_dir;
            end
            // a new message discards an uncommitted early result (its price field never completed); the early clock
            // of this message sets it again
            if (msg_px_v) pre_ok <= 1'b0;
            if (inst_v) pre_ok <= 1'b0;
            if (pre) pre_ok <= 1'b1;
        end
        if (pre) begin
            c_bpx <= bk_bid_px; c_bsz <= bk_bid_sz; c_apx <= bk_ask_px; c_asz <= bk_ask_sz;
            c_e <= e; c_ofi <= ofi_new; c_tr <= tr_new; c_dir <= dir_new;
            feat <= {dir_new, fofi, ftr, fimb, fspr, fa, fb};
        end
    end
endmodule
