// Board top: jtag_bus, reset generator, reference clock buffer and the register core.
module p5_async_fifo_soak (
    input  logic       clk_c3,
    input  logic       gt_refclk0_p,
    input  logic       gt_refclk0_n,
    output logic       sfp_tx_disable,
    output logic [1:0] led
);
    logic        clk_gt, rst_c3, rst_gt;
    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata, build_word;
    logic        cfgclk, datavalid;

    // gt_refclk0 to a fabric clock: clock-network primitives instantiated here (as in refclk_buf).
    logic refclk, refclk_div2;
    IBUFDS_GTE4 #(.REFCLK_EN_TX_PATH(1'b0), .REFCLK_HROW_CK_SEL(2'b00), .REFCLK_ICNTL_RX(2'b00)) u_ibuf (
        .I(gt_refclk0_p), .IB(gt_refclk0_n), .CEB(1'b0), .O(refclk), .ODIV2(refclk_div2));
    BUFG_GT u_bufg (.CE(1'b1), .CEMASK(1'b0), .CLR(1'b0), .CLRMASK(1'b0), .DIV(3'b000),
        .I(refclk_div2), .O(clk_gt));
    /* verilator lint_off UNUSEDSIGNAL */
    wire unused_refclk = refclk;
    /* verilator lint_on UNUSEDSIGNAL */
    rst_gen u_rst (.clk_c3(clk_c3), .clk_gt(clk_gt), .rst_c3(rst_c3), .rst_gt(rst_gt));

    USR_ACCESSE2 u_usr (.CFGCLK(cfgclk), .DATA(build_word), .DATAVALID(datavalid));
    /* verilator lint_off UNUSEDSIGNAL */
    wire unused_usr = cfgclk ^ datavalid;
    /* verilator lint_on UNUSEDSIGNAL */

    jtag_bus u_jtag (.clk(clk_c3), .rst(rst_c3), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                     .h_wdata(h_wdata), .h_rdata(h_rdata));

    fifo_core u_core (
        .clk_c3(clk_c3), .clk_gt(clk_gt), .rst_c3(rst_c3), .rst_gt(rst_gt),
        .h_we(h_we), .h_re(h_re), .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata),
        .build_word(build_word), .sfp_tx_disable(sfp_tx_disable), .led(led));
endmodule
