// fxp_round_fv: proof harness for the rounding variants (brief 139b), checked by SymbiYosys with the slang front end.
//   Same structure as divider_fv. The reference is written from the definitions with wide signed arithmetic: floor = x >>> S,
//   fraction = x - floor * 2**S, half = 2**(S-1); truncate floor; half up floor + (fraction >= half); convergent floor + (fraction > half
//   or fraction = half with floor odd); then wrap or saturate to W_OUT bits. It shares no code with the RTL (the RTL folds the rounding into a carry).
//   P1 timing, P2 value, P3 (VARIANT_B >= 0) variants agree.
module fxp_round_fv #(
    parameter int VARIANT   = 0,
    parameter int VARIANT_B = -1,
    parameter int W_IN      = 8,
    parameter int S         = 2,
    parameter int W_OUT     = 6,
    parameter int MODE      = 2,
    parameter int SAT       = 1,
    parameter int LAT       = 1
) (
    input logic            clk,
    input logic            rst,
    input logic            in_valid,
    input logic [W_IN-1:0] in_data
);
    localparam int WW = W_IN + 4;         // wide enough for the rounded value and the saturation limits

    logic first = 1'b1;
    always_ff @(posedge clk) first <= 1'b0;
    always_comb a1_reset_first: assume (first == rst);

    logic              in_ready_a, out_valid_a;
    logic [W_OUT-1:0]  out_a;
    fxp_round_sel #(.VARIANT(VARIANT), .W_IN(W_IN), .S(S), .W_OUT(W_OUT), .MODE(MODE), .SAT(SAT != 0)) dut_a
        (.clk, .rst, .in_valid, .in_ready(in_ready_a), .in_data, .out_valid(out_valid_a), .out_data(out_a));

    if (VARIANT_B >= 0) begin : g_pair
        logic             in_ready_b, out_valid_b;
        logic [W_OUT-1:0] out_b;
        fxp_round_sel #(.VARIANT(VARIANT_B), .W_IN(W_IN), .S(S), .W_OUT(W_OUT), .MODE(MODE), .SAT(SAT != 0)) dut_b
            (.clk, .rst, .in_valid, .in_ready(in_ready_b), .in_data, .out_valid(out_valid_b), .out_data(out_b));
        always_comb p3_valid_agree: assert (first || out_valid_a == out_valid_b);
        always_comb p3_data_agree:  assert (first || !out_valid_a || out_a == out_b);
        always_comb a2_ready:       assume (in_ready_a && in_ready_b);
    end

    logic             hv [LAT];
    logic [W_IN-1:0]  hd [LAT];
    always_ff @(posedge clk) begin
        hv[0] <= !rst && in_valid && in_ready_a;
        hd[0] <= in_data;
        for (int i = 1; i < LAT; i++) begin
            hv[i] <= hv[i-1] && !rst;
            hd[i] <= hd[i-1];
        end
    end

    logic signed [WW-1:0] xs, fl, frac, half, r, lo, hi, fitted;
    logic [W_OUT-1:0]     y_ref;
    always_comb begin
        xs   = WW'($signed(hd[LAT-1]));
        fl   = xs >>> S;
        frac = xs - (fl <<< S);
        half = (S == 0) ? WW'(0) : (WW'(1) <<< (S == 0 ? 0 : S - 1));
        r    = fl;
        if (S > 0 && MODE == 1 && frac >= half) r = fl + WW'(1);
        if (S > 0 && MODE == 2 && (frac > half || (frac == half && fl[0]))) r = fl + WW'(1);
        lo   = -(WW'(1) <<< (W_OUT - 1));
        hi   = (WW'(1) <<< (W_OUT - 1)) - WW'(1);
        fitted = (SAT != 0) ? ((r < lo) ? lo : (r > hi) ? hi : r) : r;
        y_ref  = fitted[W_OUT-1:0];
    end
    always_comb p1_timing: assert (first || out_valid_a == hv[LAT-1]);
    always_comb p2_value:  assert (first || !out_valid_a || out_a == y_ref);
endmodule
