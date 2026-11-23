// divider_hr_fv: proof harness for the high-radix divider variants (brief 139c), checked by SymbiYosys with the slang front end.
//   The inputs are assumed normalised (a and b have their MSB set): the function is defined for those only.
//   Reference (REF = 1): the result for the input accepted LAT cycles ago is a * 4**K = quo * b + rem with 0 <= rem < b (so quo = floor(a * 4**K / b)),
//   and out_valid is high exactly LAT cycles after an accepted input. This is a characterisation, not an algorithm: it shares no code with the RTL.
//   Pair (VARIANT_B >= 0): two variants with the same latency and protocol give the same in_ready, out_valid and out_data in every cycle.
module divider_hr_fv #(
    parameter int VARIANT   = 0,
    parameter int VARIANT_B = -1,
    parameter int W         = 7,
    parameter int K         = 3,
    parameter int PIPE      = 1,
    parameter int PIPE_B    = 1,
    parameter int LAT       = 6,
    parameter bit REF       = 1'b1
) (
    input logic           clk,
    input logic           rst,
    input logic           in_valid,
    input logic [2*W-1:0] in_data
);
    localparam int QW = 2 * K + 1;
    localparam int OW = QW + W;
    localparam int PW = QW + W + 2;

    logic first = 1'b1;
    always_ff @(posedge clk) first <= 1'b0;
    always_comb a1_reset_first: assume (first == rst);
    always_comb a2_normalised: assume (in_data[2*W-1] && in_data[W-1]);

    logic          in_ready_a, out_valid_a;
    logic [OW-1:0] out_a;
    divider_hr_sel #(.VARIANT(VARIANT), .W(W), .K(K), .PIPE(PIPE)) dut_a (.clk, .rst, .in_valid, .in_ready(in_ready_a), .in_data, .out_valid(out_valid_a), .out_data(out_a));

    if (VARIANT_B >= 0) begin : g_pair
        logic          in_ready_b, out_valid_b;
        logic [OW-1:0] out_b;
        divider_hr_sel #(.VARIANT(VARIANT_B), .W(W), .K(K), .PIPE(PIPE_B)) dut_b (.clk, .rst, .in_valid, .in_ready(in_ready_b), .in_data, .out_valid(out_valid_b), .out_data(out_b));
        always_comb p3_ready_agree: assert (first || in_ready_a == in_ready_b);
        always_comb p3_valid_agree: assert (first || out_valid_a == out_valid_b);
        always_comb p3_data_agree:  assert (first || !out_valid_a || out_a == out_b);
    end

    logic           hv [LAT];
    logic [2*W-1:0] hd [LAT];
    always_ff @(posedge clk) begin
        hv[0] <= !rst && in_valid && in_ready_a;
        hd[0] <= in_data;
        for (int i = 1; i < LAT; i++) begin
            hv[i] <= hv[i-1] && !rst;
            hd[i] <= hd[i-1];
        end
    end

    logic [QW-1:0] quo;
    logic [W-1:0]  rem;
    logic [PW-1:0] a_w, b_w, lhs, rhs;
    always_comb begin
        {quo, rem} = out_a;
        a_w = PW'(hd[LAT-1][2*W-1:W]);
        b_w = PW'(hd[LAT-1][W-1:0]);
        lhs = a_w << (2 * K);
        rhs = PW'(quo) * b_w + PW'(rem);
    end
    if (REF) begin : g_ref
        always_comb p1_timing: assert (first || out_valid_a == hv[LAT-1]);
        always_comb p2_value:  assert (first || !out_valid_a || (lhs == rhs && PW'(rem) < b_w));
    end
endmodule
