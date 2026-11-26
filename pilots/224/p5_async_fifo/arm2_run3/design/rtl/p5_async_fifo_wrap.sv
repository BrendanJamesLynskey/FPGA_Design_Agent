// Thin simulated toplevel: the register core (fifo_core) holds both clock domains and their CDC primitives.
/* verilator lint_off DECLFILENAME */
module p5_async_fifo_core #(
    parameter logic [31:0] DESIGN_ID = 32'd546635777,
    parameter logic [30:0] PRBS_SEED = 31'h7FFFFFFF,
    parameter int          SLOW_READ_DIV_CYCLES = 8
) (
    input  logic        clk_25,
    input  logic        gt_refclk,
    input  logic        rst,
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    fifo_core #(.DESIGN_ID(DESIGN_ID), .PRBS_SEED(PRBS_SEED), .SLOW_READ_DIV_CYCLES(SLOW_READ_DIV_CYCLES)) u_core (
        .clk_25(clk_25), .gt_refclk(gt_refclk), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
        .h_wdata(h_wdata), .h_rdata(h_rdata), .led(led), .sfp_tx_disable(sfp_tx_disable));
endmodule
