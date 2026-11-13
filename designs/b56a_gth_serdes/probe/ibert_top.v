// ibert_top.v (brief 56A probe): a routable wrapper for the IBERT for UltraScale GTH core on the KR260's quad 224: the reference through IBUFDS_GTE4,
// a 25 MHz system clock through a BUFG, and the four channels' pins. Probe only; nothing here is a design.
module ibert_top (
    input  wire       clk_25,
    input  wire       refclk_p,
    input  wire       refclk_n,
    input  wire [3:0] rxp,
    input  wire [3:0] rxn,
    output wire [3:0] txp,
    output wire [3:0] txn
);
    wire clk, ref0, clk_i;
    IBUF  u_ib (.I(clk_25), .O(clk_i));
    BUFG  u_bg (.I(clk_i), .O(clk));
    IBUFDS_GTE4 #(.REFCLK_EN_TX_PATH(1'b0), .REFCLK_HROW_CK_SEL(2'b00), .REFCLK_ICNTL_RX(2'b00)) u_ref (
        .I(refclk_p), .IB(refclk_n), .CEB(1'b0), .O(ref0), .ODIV2());
    p_ibert_gth u_ibert (
        .txn_o(txn), .txp_o(txp), .rxoutclk_o(), .rxn_i(rxn), .rxp_i(rxp),
        .gtrefclk0_i(ref0), .gtrefclk1_i(1'b0), .gtnorthrefclk0_i(1'b0), .gtnorthrefclk1_i(1'b0), .gtsouthrefclk0_i(1'b0), .gtsouthrefclk1_i(1'b0),
        .gtrefclk00_i(1'b0), .gtrefclk10_i(1'b0), .gtrefclk01_i(1'b0), .gtrefclk11_i(1'b0),
        .gtnorthrefclk00_i(1'b0), .gtnorthrefclk10_i(1'b0), .gtnorthrefclk01_i(1'b0), .gtnorthrefclk11_i(1'b0),
        .gtsouthrefclk00_i(1'b0), .gtsouthrefclk10_i(1'b0), .gtsouthrefclk01_i(1'b0), .gtsouthrefclk11_i(1'b0),
        .clk(clk));
endmodule
