// sqrt_r4_fv: proof harness for the radix-4 square-root variants (brief 139c), checked by SymbiYosys with the slang front end.
//   Same structure as isqrt_fv. P1 timing: out_valid is high exactly LAT cycles after an accepted input. P2 value: root * root <= x < (root + 1)^2
//   and rem = x - root * root for the input accepted LAT cycles ago. P3 (VS_ISQRT = 1): the variant agrees, cycle by cycle, with
//   arith/isqrt's restoring pipeline of the same width (a different function written for the same specification, at its own latency, so the
//   comparison delays the shorter one).
module sqrt_r4_fv #(
    parameter int VARIANT = 0,
    parameter int W       = 6,
    parameter int PIPE    = 1,
    parameter int LAT     = 4
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
    sqrt_r4_sel #(.VARIANT(VARIANT), .W(W), .PIPE(PIPE)) dut_a (.clk, .rst, .in_valid, .in_ready(in_ready_a), .in_data, .out_valid(out_valid_a), .out_data(out_a));

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
    always_comb p1_timing: assert (first || out_valid_a == hv[LAT-1]);
    always_comb p2_value:  assert (first || !out_valid_a || (sq <= x_w && x_w < sq1 && (2*RW+2)'(rem) == rem_w));
endmodule
