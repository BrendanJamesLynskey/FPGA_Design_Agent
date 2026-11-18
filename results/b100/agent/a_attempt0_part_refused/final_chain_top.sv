// chain_top.sv: the transmit latency chain of brief 96 on the K26, for brief 100's placement and routing comparisons.
// Brief 96's own mac64_tx and pcs_tx, unchanged, between a shift-register frame source and a bare GTHE4_CHANNEL (X0Y6, the SFP+ lane of
// the KR260) whose TXDATA they drive: the registers on the wire-to-wire path are the MAC's x_d/x_c, the PCS's gt_d and the GT's TXDATA
// input (design.md section 3 of b96_kr260_10g). One clock, as in 96: TXUSRCLK2 = TXUSRCLK = clk (a BUFG here; 96 uses BUFG_GT).
// Not a working link (no reference clock, no QPLL, no reset sequence): it exists so that Vivado times the TXDATA pins and the clock
// region around the GT, which is what the latency-critical chain feeds.
module chain_top (
    input  logic clk,
    input  logic din,
    input  logic rx_p,
    input  logic rx_n,
    output logic tx_p,
    output logic tx_n
);
    logic        clk_g;
    logic [79:0] sh;
    logic        rst, adv, s_ready, sop, eop, underrun;
    logic [63:0] x_d, gt_d;
    logic [7:0]  x_c;
    BUFG u_bg (.I(clk), .O(clk_g));
    always_ff @(posedge clk_g) begin sh <= {sh[78:0], din}; rst <= sh[79]; end   // the reset is a register, as in 96 (u_rst)
    mac64_tx u_mac (.clk(clk_g), .rst(rst), .adv(adv), .s_valid(sh[64]), .s_data(sh[63:0]), .s_last(sh[65]), .s_nb1(sh[68:66]),
                    .s_poison(sh[69]), .s_ready(s_ready), .x_d(x_d), .x_c(x_c), .sop(sop), .eop(eop), .underrun(underrun));
    pcs_tx u_pcs (.clk(clk_g), .rst(rst), .x_d(x_d), .x_c(x_c), .adv(adv), .gt_d(gt_d));
    (* DONT_TOUCH = "true" *)
    GTHE4_CHANNEL u_gt (
        .GTHRXP(rx_p), .GTHRXN(rx_n), .GTHTXP(tx_p), .GTHTXN(tx_n),
        .TXUSRCLK(clk_g), .TXUSRCLK2(clk_g), .RXUSRCLK(clk_g), .RXUSRCLK2(clk_g),
        .TXDATA({64'd0, gt_d}), .TXCTRL0({15'd0, adv}), .TXCTRL1({15'd0, s_ready}), .TXCTRL2({7'd0, sop, eop, underrun, 5'd0}));
endmodule
