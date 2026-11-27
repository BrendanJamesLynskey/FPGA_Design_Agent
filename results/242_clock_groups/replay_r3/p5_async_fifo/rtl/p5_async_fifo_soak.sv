// p5_async_fifo_soak: board top. jtag_bus (supplied, unchanged), power-on reset, the register core,
// and the reader clock from the SFP+ MGTREFCLK0 pair (IBUFDS_GTE4 + BUFG_GT, no GT channel).
module p5_async_fifo_soak #(
    parameter int RESET_HOLD_CYCLES = 16
) (
    input  logic       clk_25mhz,
    input  logic       gt_refclk_p,
    input  logic       gt_refclk_n,
    output logic [1:0] led,
    output logic       sfp_tx_disable
);
    logic        rst;
    /* verilator lint_off UNUSEDSIGNAL */
    logic        refclk;
    /* verilator lint_on UNUSEDSIGNAL */
    logic        refclk_div2;
    logic        clk_rd;
    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata;

    rst_gen #(.RESET_HOLD_CYCLES(RESET_HOLD_CYCLES)) u_rst (.clk(clk_25mhz), .rst(rst));

    jtag_bus u_jtag (.clk(clk_25mhz), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                     .h_wdata(h_wdata), .h_rdata(h_rdata));

    // ODIV2 (HROW_CK_SEL 2'b00: same frequency as O) is the output that may drive a BUFG_GT (DRC REQP-1926/1929).
    IBUFDS_GTE4 #(.REFCLK_EN_TX_PATH(1'b0), .REFCLK_HROW_CK_SEL(2'b00), .REFCLK_ICNTL_RX(2'b00)) u_refclk (
        .O(refclk), .ODIV2(refclk_div2), .CEB(1'b0), .I(gt_refclk_p), .IB(gt_refclk_n));

    BUFG_GT u_bufg (.O(clk_rd), .CE(1'b1), .CEMASK(1'b0), .CLR(1'b0), .CLRMASK(1'b0), .DIV(3'b000), .I(refclk_div2));

    p5_async_fifo_soak_core u_core (
        .clk_wr(clk_25mhz), .clk_rd(clk_rd),
        .h_we(h_we), .h_re(h_re), .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata),
        .led(led), .sfp_tx_disable(sfp_tx_disable));
endmodule
