// Thin top: MMCM (25 -> 250 MHz), reset generator, jtag_bus and the register core.
module fir32_top (
    input  logic       clk_25,
    output logic [1:0] led,
    output logic       sfp_tx_disable
);
    logic clk_fb, clk_dp_raw, clk_dp, locked;
    MMCME4_BASE #(
        .BANDWIDTH("OPTIMIZED"), .CLKFBOUT_MULT_F(40.0), .CLKIN1_PERIOD(40.0),
        .CLKOUT0_DIVIDE_F(4.0), .DIVCLK_DIVIDE(1)
    ) u_mmcm (
        .CLKIN1(clk_25), .CLKFBIN(clk_fb), .PWRDWN(1'b0), .RST(1'b0),
        .CLKOUT0(clk_dp_raw), .CLKFBOUT(clk_fb), .LOCKED(locked)
    );
    BUFG u_bufg (.O(clk_dp), .I(clk_dp_raw));

    logic rst_bus, rst_dp;
    reset_gen u_rst (.clk_bus(clk_25), .clk_dp(clk_dp), .locked(locked),
                     .rst_bus(rst_bus), .rst_dp(rst_dp));

    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata;
    jtag_bus u_jtag (.clk(clk_25), .rst(rst_bus), .h_we(h_we), .h_re(h_re),
                     .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata));

    fir32_core u_core (
        .clk_bus(clk_25), .clk_dp(clk_dp), .rst_bus(rst_bus), .rst_dp(rst_dp),
        .h_we(h_we), .h_re(h_re), .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata),
        .led(led), .sfp_tx_disable(sfp_tx_disable)
    );
endmodule
