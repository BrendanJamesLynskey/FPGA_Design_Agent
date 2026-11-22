// isqrt_fv: proof harness for the square-root variants (brief 139b), checked by SymbiYosys with the slang front end.
//   Same structure as divider_fv. The reference is a characterisation, not an algorithm: the result is correct exactly when
//   root * root <= x < (root + 1) * (root + 1) and rem = x - root * root (so any two correct variants agree, and neither shares code with the RTL).
//   P1 timing: out_valid is high exactly LAT cycles after an accepted input. P2 value: the characterisation holds for the input accepted LAT cycles ago.
//   P3 (VARIANT_B >= 0): the two variants agree on out_valid and out_data.
module isqrt_fv #(
    parameter int VARIANT   = 0,
    parameter int VARIANT_B = -1,
    parameter int W         = 6,
    parameter int PIPE      = 1,
    parameter int PIPE_B    = 1,
    parameter int LAT       = 4,
    parameter bit REF       = 1'b1
) (
    input logic         clk,
    input logic         rst,
    input logic         in_valid,
    input logic [W-1:0] in_data
);
    localparam int RW = (W + 1) / 2;
    localparam int OW = 2 * RW + 1;

    logic first = 1'b1;
    always_ff @(posedge clk) first <= 1'b0;
    always_comb a1_reset_first: assume (first == rst);

    logic          in_ready_a, out_valid_a;
    logic [OW-1:0] out_a;
    isqrt_sel #(.VARIANT(VARIANT), .W(W), .PIPE(PIPE)) dut_a (.clk, .rst, .in_valid, .in_ready(in_ready_a), .in_data, .out_valid(out_valid_a), .out_data(out_a));

    if (VARIANT_B >= 0) begin : g_pair
        logic          in_ready_b, out_valid_b;
        logic [OW-1:0] out_b;
        isqrt_sel #(.VARIANT(VARIANT_B), .W(W), .PIPE(PIPE_B)) dut_b (.clk, .rst, .in_valid, .in_ready(in_ready_b), .in_data, .out_valid(out_valid_b), .out_data(out_b));
        always_comb p3_valid_agree: assert (first || out_valid_a == out_valid_b);
        always_comb p3_data_agree:  assert (first || !out_valid_a || out_a == out_b);
        always_comb a2_ready:       assume (in_ready_a && in_ready_b);
    end

    logic         hv [LAT];
    logic [W-1:0] hd [LAT];
    always_ff @(posedge clk) begin
        hv[0] <= !rst && in_valid && in_ready_a;
        hd[0] <= in_data;
        for (int i = 1; i < LAT; i++) begin
            hv[i] <= hv[i-1] && !rst;
            hd[i] <= hd[i-1];
        end
    end

    logic [RW-1:0]   root;
    logic [RW:0]     rem;
    logic [2*RW+1:0] x_w, sq, sq1, rem_w;
    always_comb begin
        {root, rem} = out_a;
        x_w   = (2*RW+2)'(hd[LAT-1]);
        sq    = (2*RW+2)'(root) * (2*RW+2)'(root);
        sq1   = ((2*RW+2)'(root) + (2*RW+2)'(1)) * ((2*RW+2)'(root) + (2*RW+2)'(1));
        rem_w = x_w - sq;
    end
    if (REF) begin : g_ref
        always_comb p1_timing: assert (first || out_valid_a == hv[LAT-1]);
        always_comb p2_value:  assert (first || !out_valid_a || (sq <= x_w && x_w < sq1 && (2*RW+2)'(rem) == rem_w));
    end
endmodule
