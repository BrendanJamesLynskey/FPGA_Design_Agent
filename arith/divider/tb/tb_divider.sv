// tb_divider: connects divider_sel to the generic stream harness (brief 139b). Parameters are set on the command line by arith/common/sim.py.
`timescale 1ns/1ps
module tb_divider #(
    parameter int VARIANT = 0,
    parameter int W       = 8,
    parameter int PIPE    = 1,
    parameter int IN_W    = 16,
    parameter int OUT_W   = 16,
    parameter int NVEC    = 16,
    parameter int LAT     = 1,
    parameter int GAP_PCT = 0,
    parameter int SEED    = 1,
    parameter int WRAP    = 0        // 1: simulate through the out-of-context wrapper (two more clocks of latency)
);
    logic clk, rst, in_valid, in_ready, out_valid;
    logic [IN_W-1:0]  in_data;
    logic [OUT_W-1:0] out_data;
    tb_stream #(.IN_W(IN_W), .OUT_W(OUT_W), .NVEC(NVEC), .LAT(LAT), .GAP_PCT(GAP_PCT), .SEED(SEED))
        h (.clk, .rst, .in_valid, .in_ready, .in_data, .out_valid, .out_data);
    if (WRAP != 0) begin : g_wrap
        divider_ooc #(.VARIANT(VARIANT), .W(W), .PIPE(PIPE)) dut (.clk, .rst, .in_valid, .in_ready, .in_data, .out_valid, .out_data);
    end else begin : g_core
        divider_sel #(.VARIANT(VARIANT), .W(W), .PIPE(PIPE)) dut (.clk, .rst, .in_valid, .in_ready, .in_data, .out_valid, .out_data);
    end
endmodule
