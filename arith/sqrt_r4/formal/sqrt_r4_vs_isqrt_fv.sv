// sqrt_r4_vs_isqrt_fv: the radix-4 pipeline against arith/isqrt's restoring pipeline, output to output (brief 139c).
//   Both are free-running pipelines with PIPE_A and PIPE_B steps per stage, so their latencies differ; the one with the shorter latency is
//   delayed by the difference. The claim: for every input sequence from reset the two results are equal whenever both are valid.
module sqrt_r4_vs_isqrt_fv #(
    parameter int W      = 8,
    parameter int PIPE_A = 1,
    parameter int PIPE_B = 1,
    parameter int LAT_A  = 2,     // latency of sqrt_r4_sel (pipe)
    parameter int LAT_B  = 4      // latency of isqrt_sel (restoring_pipe)
) (
    input logic         clk,
    input logic         rst,
    input logic         in_valid,
    input logic [W-1:0] in_data
);
    localparam int RW = (W + 1) / 2;
    localparam int OW = 2 * RW + 1;
    localparam int LM = (LAT_A > LAT_B) ? LAT_A : LAT_B;

    logic first = 1'b1;
    always_ff @(posedge clk) first <= 1'b0;
    always_comb a1_reset_first: assume (first == rst);

    logic          rdy_a, rdy_b, ov_a, ov_b;
    logic [OW-1:0] od_a, od_b;
    sqrt_r4_sel #(.VARIANT(1), .W(W), .PIPE(PIPE_A)) dut_a (.clk, .rst, .in_valid, .in_ready(rdy_a), .in_data, .out_valid(ov_a), .out_data(od_a));
    isqrt_sel   #(.VARIANT(1), .W(W), .PIPE(PIPE_B)) dut_b (.clk, .rst, .in_valid, .in_ready(rdy_b), .in_data, .out_valid(ov_b), .out_data(od_b));

    // delay the earlier output by the latency difference
    logic          dv [LM+1];
    logic [OW-1:0] dd [LM+1];
    always_comb begin
        dv[0] = (LAT_A < LAT_B) ? ov_a : ov_b;
        dd[0] = (LAT_A < LAT_B) ? od_a : od_b;
    end
    always_ff @(posedge clk) begin
        for (int i = 1; i <= LM; i++) begin
            dv[i] <= dv[i-1] && !rst;
            dd[i] <= dd[i-1];
        end
    end
    localparam int DIFF = (LAT_A > LAT_B) ? (LAT_A - LAT_B) : (LAT_B - LAT_A);
    logic          lv;
    logic [OW-1:0] ld, hd_;
    always_comb begin
        lv  = (LAT_A < LAT_B) ? ov_b : ov_a;
        ld  = (LAT_A < LAT_B) ? od_b : od_a;
        hd_ = dd[DIFF];
    end
    always_comb p_same_valid: assert (first || lv == dv[DIFF]);
    always_comb p_same_data:  assert (first || !lv || ld == hd_);
endmodule
