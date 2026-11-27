// Board top: jtag_bus, power-up reset generator, GT reference clock divider, register core.
module p6_clkmux_top #(
    parameter int unsigned B_DIV = 2
) (
    input  logic       clk_c3,
    input  logic       gt_refclk_p,
    input  logic       gt_refclk_n,
    output logic       sfp_tx_disable,
    output logic [1:0] led
);
    // power-up reset: a few clocks, no reset input
    /* verilator lint_off SYNCASYNCNET */
    logic [3:0] rst_sr = 4'hF;
    always_ff @(posedge clk_c3) rst_sr <= {rst_sr[2:0], 1'b0};
    wire rst = rst_sr[3];
    /* verilator lint_on SYNCASYNCNET */

    // clock B: GT reference clock divided by B_DIV
    logic refclk, refclk_div2;
    IBUFDS_GTE4 #(.REFCLK_HROW_CK_SEL(2'b00)) u_refclk (
        .I(gt_refclk_p), .IB(gt_refclk_n), .CEB(1'b0), .O(refclk), .ODIV2(refclk_div2));
    logic clk_b;
    BUFG_GT u_bufg_gt (
        .I(refclk), .CE(1'b1), .CEMASK(1'b0), .CLR(1'b0), .CLRMASK(1'b0),
        .DIV(3'(B_DIV - 1)), .O(clk_b));
    /* verilator lint_off UNUSEDSIGNAL */
    wire unused_div2 = refclk_div2;
    /* verilator lint_on UNUSEDSIGNAL */

    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata;

    jtag_bus u_jtag (.clk(clk_c3), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                     .h_wdata(h_wdata), .h_rdata(h_rdata));

`ifndef SYNTHESIS
    // simulation lint only: mark the supplied bus's sim-unused nets as read
    /* verilator lint_off UNUSEDSIGNAL */
    wire unused_jtag = u_jtag.tdo ^ u_jtag.cmd_s[45];
    /* verilator lint_on UNUSEDSIGNAL */
`endif

    p6_clkmux_core #(.B_DIV(B_DIV)) u_core (
        .clk(clk_c3), .clk_b(clk_b), .rst(rst),
        .h_we(h_we), .h_re(h_re), .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata),
        .led(led), .sfp_tx_disable(sfp_tx_disable));
endmodule
