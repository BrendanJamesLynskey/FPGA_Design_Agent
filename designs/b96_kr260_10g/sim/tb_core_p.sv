`timescale 1ns/1fs
// tb_core_p.sv: bench top for b96_core with the behavioural GT stand-in (sim/gth_wiz_model96.sv): the whole 10G path in one clock domain pair
// (both user clocks are the reference). The cocotb bench drives the host bus like the JTAG front end does.
module tb_core_p #(
    parameter bit NEAR_END = 1'b1,
    parameter bit TRADE = 1'b1,
    parameter bit RATE_MATCH = 1'b1,
    parameter bit RM_OWN = 1'b0
) (
    input  logic        clk, refclk, rst,
    input  logic        h_we, h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic        sfp_tx_disable,
    output logic [1:0]  led
);
    logic tx_p, tx_n, scl_low, sda_low, sm_en;
    logic [7:0] sm_addr;
    b96_core #(.BUILD_STAMP(32'h96), .NEAR_END(NEAR_END), .TRADE(TRADE), .RATE_MATCH(RATE_MATCH), .RM_OWN(RM_OWN)) u (.clk, .rst, .h_we, .h_re, .h_addr, .h_wdata, .h_rdata, .refclk,
        .rx_p(1'b0), .rx_n(1'b1), .tx_p, .tx_n, .sfp_tx_disable, .sfp_mod_abs(1'b0), .sfp_rx_los(1'b0), .sfp_tx_fault(1'b0),
        .i2c_scl_low(scl_low), .i2c_sda_low(sda_low), .i2c_scl_i(1'b1), .i2c_sda_i(1'b1), .sm_en, .sm_addr, .sm_do(16'h0), .sm_rdy(sm_en), .led);
endmodule
