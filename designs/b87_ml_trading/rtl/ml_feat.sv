// ml_feat.sv: the decision model's features, computed in the fabric from the 58A book read and the message stream.
//
// At each message's decision point (msg_px_v) for the tracked instrument (ml_inst), the book entry read for that
// message (bk_*, the book BEFORE this message, i.e. after the previous one) is the newest snapshot S. One update:
//   - the order-flow-imbalance term between the previous snapshot P and S (Cont, Kukanov and Stoikov 2014),
//     clipped to -127..127, enters a 16-term window;
//   - the trade sign of the PREVIOUS tracked message (+1 a TRADE on the ask side, i.e. a buyer; -1 on the bid side;
//     nothing for other types) enters an 8-term window;
//   - the direction of the last mid change is updated from P to S.
// The features are then taken from S and the windows, packed as model/lobsim.py documents, and registered:
// feat_v / feat follow msg_px_v by one clock. model/lobsim.py FeatureState is the bit-exact reference (update(S,
// sign of the previous message)). An empty side (price 0) gives size 0 and spread 15.
// Other instruments do not touch the state and give no feat_v. Reset clears the state (sizes and prices 0).

module ml_feat (
    input  logic        clk,
    input  logic        rst,
    input  logic [15:0] ml_inst,
    input  logic        msg_px_v,
    input  logic [7:0]  msg_type,
    input  logic        msg_side,
    input  logic [15:0] msg_inst,
    input  logic        bk_valid,
    input  logic [31:0] bk_bid_px, bk_bid_sz, bk_ask_px, bk_ask_sz,
    output logic        feat_v,
    output logic [37:0] feat
);
    localparam logic [7:0] TRADE = 8'd4;
    logic        go;
    assign go = msg_px_v && bk_valid && msg_inst == ml_inst;

    // state
    logic [31:0]        p_bpx, p_bsz, p_apx, p_asz;
    logic signed [7:0]  ofi_w [16];
    logic signed [11:0] ofi_sum;
    logic signed [1:0]  tr_w [8];
    logic signed [4:0]  tr_sum;
    logic signed [1:0]  pend_sign;
    logic [1:0]         last_dir;

    // the OFI term of this update
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

    // direction of the mid change P -> S (sums in 33 bits)
    logic [32:0] mid_p, mid_s;
    assign mid_p = {1'b0, p_bpx} + {1'b0, p_apx};
    assign mid_s = {1'b0, bk_bid_px} + {1'b0, bk_ask_px};
    logic [1:0] dir_new;
    assign dir_new = mid_s > mid_p ? 2'd2 : (mid_s < mid_p ? 2'd0 : last_dir);

    // features from S
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
    assign ftr  = 5'(tr_new + 5'sd8);
    assign fofi = ofi_new > 12'sd127 ? 8'd255 : (ofi_new < -12'sd127 ? 8'd1 : 8'(ofi_new + 12'sd128));

    always_ff @(posedge clk) begin
        if (rst) begin
            p_bpx <= '0; p_bsz <= '0; p_apx <= '0; p_asz <= '0;
            for (int i = 0; i < 16; i++) ofi_w[i] <= '0;
            for (int i = 0; i < 8; i++) tr_w[i] <= '0;
            ofi_sum <= '0; tr_sum <= '0; pend_sign <= '0; last_dir <= 2'd1;
            feat_v <= 1'b0;
        end else begin
            feat_v <= go;
            if (go) begin
                p_bpx <= bk_bid_px; p_bsz <= bk_bid_sz; p_apx <= bk_ask_px; p_asz <= bk_ask_sz;
                for (int i = 0; i < 15; i++) ofi_w[i] <= ofi_w[i + 1];
                ofi_w[15] <= e;
                ofi_sum <= ofi_new;
                if (pend_sign != 0) begin
                    for (int i = 0; i < 7; i++) tr_w[i] <= tr_w[i + 1];
                    tr_w[7] <= pend_sign;
                    tr_sum <= tr_new;
                end
                pend_sign <= (msg_type == TRADE) ? (msg_side ? 2'sd1 : -2'sd1) : 2'sd0;
                last_dir <= dir_new;
                feat <= {dir_new, fofi, ftr_eff(pend_sign, ftr, tr_sum), fimb, fspr, fa, fb};
            end
        end
    end

    // the trade window only moves when the previous message was a trade
    function automatic logic [4:0] ftr_eff(input logic signed [1:0] ps, input logic [4:0] moved,
                                           input logic signed [4:0] sum);
        ftr_eff = (ps != 0) ? moved : 5'(sum + 5'sd8);
    endfunction
endmodule
