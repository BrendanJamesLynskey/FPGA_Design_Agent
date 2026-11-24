// fxp_round_sel: selects one rounding variant behind one packed stream interface (brief 139b).
//   VARIANT 0 fold (latency 1), 1 inc (latency 1), 2 two-stage (latency 2). in_data = x, out_data = y.
module fxp_round_sel #(
    parameter int VARIANT = 0,
    parameter int W_IN    = 16,
    parameter int S       = 4,
    parameter int W_OUT   = 12,
    parameter int MODE    = 2,
    parameter bit SAT     = 1'b1
) (
    input  logic             clk,
    input  logic             rst,
    input  logic             in_valid,
    output logic             in_ready,
    input  logic [W_IN-1:0]  in_data,
    output logic             out_valid,
    output logic [W_OUT-1:0] out_data
);
    if (VARIANT == 0) begin : g_v
        fxp_round_fold #(.W_IN(W_IN), .S(S), .W_OUT(W_OUT), .MODE(MODE), .SAT(SAT)) u (.clk, .rst, .in_valid, .in_ready, .x(in_data), .out_valid, .y(out_data));
    end else if (VARIANT == 1) begin : g_v
        fxp_round_inc #(.W_IN(W_IN), .S(S), .W_OUT(W_OUT), .MODE(MODE), .SAT(SAT)) u (.clk, .rst, .in_valid, .in_ready, .x(in_data), .out_valid, .y(out_data));
    end else begin : g_v
        fxp_round_2st #(.W_IN(W_IN), .S(S), .W_OUT(W_OUT), .MODE(MODE), .SAT(SAT)) u (.clk, .rst, .in_valid, .in_ready, .x(in_data), .out_valid, .y(out_data));
    end
endmodule
