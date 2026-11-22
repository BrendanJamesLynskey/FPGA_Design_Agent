// tb_fxp_round: connects fxp_round_sel to the generic stream harness (brief 139b).
`timescale 1ns/1ps
module tb_fxp_round #(
    parameter int VARIANT = 0,
    parameter int W_IN    = 8,
    parameter int S       = 2,
    parameter int W_OUT   = 6,
    parameter int MODE    = 2,
    parameter int SAT     = 1,
    parameter int IN_W    = 8,       // equal to W_IN and W_OUT; set by sim.py for the generic harness
    parameter int OUT_W   = 6,
    parameter int NVEC    = 16,
    parameter int LAT     = 1,
    parameter int GAP_PCT = 0,
    parameter int SEED    = 1,
    parameter int WRAP    = 0        // 1: simulate through the out-of-context wrapper (two more clocks of latency)
);
    logic clk, rst, in_valid, in_ready, out_valid;
    logic [W_IN-1:0]  in_data;
    logic [W_OUT-1:0] out_data;
    tb_stream #(.IN_W(IN_W), .OUT_W(OUT_W), .NVEC(NVEC), .LAT(LAT), .GAP_PCT(GAP_PCT), .SEED(SEED))
        h (.clk, .rst, .in_valid, .in_ready, .in_data, .out_valid, .out_data);
    if (WRAP != 0) begin : g_wrap
        fxp_round_ooc #(.VARIANT(VARIANT), .W_IN(W_IN), .S(S), .W_OUT(W_OUT), .MODE(MODE), .SAT(SAT)) dut (.clk, .rst, .in_valid, .in_ready, .in_data, .out_valid, .out_data);
    end else begin : g_core
        fxp_round_sel #(.VARIANT(VARIANT), .W_IN(W_IN), .S(S), .W_OUT(W_OUT), .MODE(MODE), .SAT(SAT)) dut (.clk, .rst, .in_valid, .in_ready, .in_data, .out_valid, .out_data);
    end
endmodule
