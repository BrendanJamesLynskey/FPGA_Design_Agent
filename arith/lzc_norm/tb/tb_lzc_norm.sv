// tb_lzc_norm: connects lznorm_sel to the generic stream harness (brief 139b).
`timescale 1ns/1ps
module tb_lzc_norm #(
    parameter int VARIANT = 0,
    parameter int W       = 8,
    parameter int PIPE    = 1,
    parameter int IN_W    = 8,
    parameter int OUT_W   = 12,      // W + ceil(log2(W + 1))
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
        lzc_norm_ooc #(.VARIANT(VARIANT), .W(W), .PIPE(PIPE)) dut (.clk, .rst, .in_valid, .in_ready, .in_data, .out_valid, .out_data);
    end else begin : g_core
        lznorm_sel #(.VARIANT(VARIANT), .W(W), .PIPE(PIPE)) dut (.clk, .rst, .in_valid, .in_ready, .in_data, .out_valid, .out_data);
    end
endmodule
