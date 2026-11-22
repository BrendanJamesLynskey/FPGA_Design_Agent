// recip_fv: proof harness for the reciprocal variants (brief 139c), checked by SymbiYosys with the slang front end.
//   The input is assumed normalised (MSB set). The result for the input accepted LAT cycles ago is y (W + 1 bits); with N = 2**(2W-1) the exact value is
//   N / b and the error e = N / b - y (in units of the last place). The characterisation is a pair of products, so it shares no code with the RTL:
//     upper:  e < UP_NUM / DEN   <=>  N * DEN < (y * DEN + UP_NUM) * b
//     lower:  e > -LO_NUM / DEN  <=>  y * DEN < N * DEN + LO_NUM * b   (LO_NUM = 0 with ONE_SIDED = 1 means e >= 0: y * b <= N)
//   P1 timing: out_valid is high exactly LAT cycles after an accepted input.
module recip_fv #(
    parameter int VARIANT   = 1,
    parameter int W         = 8,
    parameter int A         = 3,
    parameter int LAT       = 5,
    parameter int DEN       = 4,
    parameter int UP_NUM    = 8,
    parameter int LO_NUM    = 0,
    parameter bit ONE_SIDED = 1'b1
) (
    input logic         clk,
    input logic         rst,
    input logic         in_valid,
    input logic [W-1:0] in_data
);
    localparam int PW = 2 * W + 20;

    logic first = 1'b1;
    always_ff @(posedge clk) first <= 1'b0;
    always_comb a1_reset_first: assume (first == rst);
    always_comb a2_normalised:  assume (in_data[W-1]);

    logic         in_ready, out_valid;
    logic [W:0]   y;
    recip_sel #(.VARIANT(VARIANT), .W(W), .A(A)) dut (.clk, .rst, .in_valid, .in_ready, .in_data, .out_valid, .out_data(y));

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

    logic [PW-1:0] n_w, b_w, y_w, up_l, up_r, lo_l, lo_r;
    always_comb begin
        n_w  = PW'(1) << (2 * W - 1);
        b_w  = PW'(hd[LAT-1]);
        y_w  = PW'(y);
        up_l = n_w * PW'(DEN);
        up_r = (y_w * PW'(DEN) + PW'(UP_NUM)) * b_w;
        lo_l = y_w * PW'(DEN) * b_w;
        lo_r = n_w * PW'(DEN) + PW'(LO_NUM) * b_w;
    end
    always_comb p1_timing: assert (first || out_valid == hv[LAT-1]);
    always_comb p2_upper:  assert (first || !out_valid || up_l < up_r);
    always_comb p3_lower:  assert (first || !out_valid || ONE_SIDED || lo_l < lo_r);
    always_comb p3_lower_one_sided: assert (first || !out_valid || !ONE_SIDED || y_w * b_w <= n_w);
endmodule
