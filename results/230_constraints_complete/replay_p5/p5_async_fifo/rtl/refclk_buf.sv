// gt_refclk0 differential pair to a fabric clock: IBUFDS_GTE4 then BUFG_GT (no transceiver channel).
module refclk_buf (
    input  logic gt_refclk0_p,
    input  logic gt_refclk0_n,
    output logic clk_gt
);
    logic refclk, refclk_div2;
    IBUFDS_GTE4 #(.REFCLK_EN_TX_PATH(1'b0), .REFCLK_HROW_CK_SEL(2'b00), .REFCLK_ICNTL_RX(2'b00)) u_ibuf (
        .I(gt_refclk0_p), .IB(gt_refclk0_n), .CEB(1'b0), .O(refclk), .ODIV2(refclk_div2));
    BUFG_GT u_bufg (.CE(1'b1), .CEMASK(1'b0), .CLR(1'b0), .CLRMASK(1'b0), .DIV(3'b000),
        .I(refclk_div2), .O(clk_gt));
    /* verilator lint_off UNUSEDSIGNAL */
    wire unused_refclk = refclk;
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
