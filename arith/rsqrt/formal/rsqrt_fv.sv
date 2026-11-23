// rsqrt_fv: proof harness for the reciprocal-square-root variants (brief 139c), checked by SymbiYosys with the slang front end.
//   The input x is assumed to lie in [2**(W-2), 2**W) (X = x / 2**(W-2) in [1, 4)). The result for the input accepted LAT cycles ago is y (W + 1 bits); the exact
//   value is Y_exact = sqrt(N / x) with N = 2**(3W-2) and the error is e = Y_exact - y in units of the last place. The characterisation compares squares, so it
//   shares no code with the RTL and needs no square root:
//     upper:  e < UP_NUM / DEN   <=>  (y * DEN + UP_NUM)**2 * x > N * DEN**2
//     lower:  e > -LO_NUM / DEN  <=>  y * DEN <= LO_NUM  or  (y * DEN - LO_NUM)**2 * x < N * DEN**2
//   P1 timing: out_valid is high exactly LAT cycles after an accepted input.
module rsqrt_fv #(
    parameter int VARIANT = 1,
    parameter int W       = 8,
    parameter int A       = 3,
    parameter int LAT     = 6,
    parameter int DEN     = 4,
    parameter int UP_NUM  = 8,
    parameter int LO_NUM  = 1
) (
    input logic         clk,
    input logic         rst,
    input logic         in_valid,
    input logic [W-1:0] in_data
);
    localparam int PW = 3 * W + 40;

    logic first = 1'b1;
    always_ff @(posedge clk) first <= 1'b0;
    always_comb a1_reset_first: assume (first == rst);
    always_comb a2_range:       assume (in_data[W-1] || in_data[W-2]);

    logic         in_ready, out_valid;
    logic [W:0]   y;
    rsqrt_sel #(.VARIANT(VARIANT), .W(W), .A(A)) dut (.clk, .rst, .in_valid, .in_ready, .in_data, .out_valid, .out_data(y));

    logic         hv [LAT];
    logic [W-1:0] hd [LAT];
    always_ff @(posedge clk) begin
        hv[0] <= !rst && in_valid && in_ready;
        hd[0] <= in_data;
        for (int i = 1; i < LAT; i++) begin
            hv[i] <= hv[i-1] && !rst;
            hd[i] <= hd[i-1];
        end
    end

    logic [PW-1:0] n_w, x_w, y_w, den2, up_s, lo_s, lhs_up, lhs_lo, rhs;
    always_comb begin
        n_w    = PW'(1) << (3 * W - 2);
        x_w    = PW'(hd[LAT-1]);
        y_w    = PW'(y);
        den2   = PW'(DEN) * PW'(DEN);
        up_s   = y_w * PW'(DEN) + PW'(UP_NUM);
        lo_s   = (y_w * PW'(DEN) > PW'(LO_NUM)) ? y_w * PW'(DEN) - PW'(LO_NUM) : '0;
        lhs_up = up_s * up_s * x_w;
        lhs_lo = lo_s * lo_s * x_w;
        rhs    = n_w * den2;
    end
    always_comb p1_timing: assert (first || out_valid == hv[LAT-1]);
    always_comb p2_upper:  assert (first || !out_valid || lhs_up > rhs);
    always_comb p3_lower:  assert (first || !out_valid || y_w * PW'(DEN) <= PW'(LO_NUM) || lhs_lo < rhs);
endmodule
