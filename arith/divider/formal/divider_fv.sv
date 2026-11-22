// divider_fv: proof harness for the divider variants (brief 139b), checked by SymbiYosys with the slang front end.
//   Free inputs: in_valid and in_data. rst is asserted in the first cycle only (assumption A1) and then low.
//   Reference: an independent expression (SystemVerilog `/` and `%`, with the spec's division-by-zero convention), delayed by the latency
//   through a history register that holds the accepted inputs. Checks, every cycle:
//     P1 out_valid is high exactly LAT cycles after an accepted input (and only then);
//     P2 when out_valid is high, out_data equals the reference of the input accepted LAT cycles ago.
//   With VARIANT_B >= 0 a second variant sees the same inputs and the same reset, and
//     P3 their out_valid agree and their out_data agree when valid (variant against variant, no reference).
module divider_fv #(
    parameter int VARIANT   = 0,
    parameter int VARIANT_B = -1,
    parameter int W         = 4,
    parameter int PIPE      = 1,
    parameter int PIPE_B    = 1,
    parameter int LAT       = 5,          // from model.latency(), passed by the test
    parameter bit REF       = 1'b1        // check against the reference (P1, P2)
) (
    input logic              clk,
    input logic              rst,
    input logic              in_valid,
    input logic [2*W-1:0]    in_data
);
    logic first = 1'b1;
    always_ff @(posedge clk) first <= 1'b0;
    always_comb a1_reset_first: assume (first == rst);

    logic          in_ready_a, out_valid_a;
    logic [2*W-1:0] out_a;
    divider_sel #(.VARIANT(VARIANT), .W(W), .PIPE(PIPE)) dut_a (.clk, .rst, .in_valid, .in_ready(in_ready_a), .in_data, .out_valid(out_valid_a), .out_data(out_a));

    if (VARIANT_B >= 0) begin : g_pair
        logic           in_ready_b, out_valid_b;
        logic [2*W-1:0] out_b;
        divider_sel #(.VARIANT(VARIANT_B), .W(W), .PIPE(PIPE_B)) dut_b (.clk, .rst, .in_valid, .in_ready(in_ready_b), .in_data, .out_valid(out_valid_b), .out_data(out_b));
        // both must accept the same inputs for the comparison to be meaningful: the pair is formed of pipelines (in_ready = 1)
        always_comb p3_valid_agree: assert (first || out_valid_a == out_valid_b);
        always_comb p3_data_agree:  assert (first || !out_valid_a || out_a == out_b);
        always_comb a2_ready:       assume (in_ready_a && in_ready_b);
    end

    // history of accepted inputs: hv[i] / hd[i] describe the input accepted i + 1 cycles ago
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

    logic [W-1:0] n, d, q_ref, r_ref;
    always_comb begin
        n     = hd[LAT-1][2*W-1:W];
        d     = hd[LAT-1][W-1:0];
        q_ref = (d == '0) ? '1 : n / d;
        r_ref = (d == '0) ? n : n % d;
    end
    if (REF) begin : g_ref
        always_comb p1_timing: assert (first || out_valid_a == hv[LAT-1]);
        always_comb p2_value:  assert (first || !out_valid_a || out_a == {q_ref, r_ref});
    end
endmodule
