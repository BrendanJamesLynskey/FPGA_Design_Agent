// top: MMCM (25 -> 100 MHz), reset generator, jtag_bus and the CRC core.
// The h_* register-port signals are internal nets in hardware. For simulation and lint
// (SYNTHESIS undefined) they are also visible as observation-only top ports, so the spec's
// port list exists on the top without adding board pins to the synthesised design.
/* verilator lint_off PINCONNECTEMPTY */
module top (
    input  logic       clk25,
    output logic [1:0] led,
`ifndef SYNTHESIS
    output logic        h_we,
    output logic        h_re,
    output logic [11:0] h_addr,
    output logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
`endif
    output logic       sfp_tx_disable
);
    logic clk_fb, clk_mmcm, clk, locked;
    MMCME4_BASE #(.CLKIN1_PERIOD(40.0), .CLKFBOUT_MULT_F(40.0), .DIVCLK_DIVIDE(1), .CLKOUT0_DIVIDE_F(10.0)) u_mmcm (
        .CLKIN1(clk25), .CLKFBIN(clk_fb), .CLKFBOUT(clk_fb), .CLKOUT0(clk_mmcm), .LOCKED(locked), .PWRDWN(1'b0), .RST(1'b0),
        .CLKFBOUTB(), .CLKOUT0B(), .CLKOUT1(), .CLKOUT1B(), .CLKOUT2(), .CLKOUT2B(), .CLKOUT3(), .CLKOUT3B(),
        .CLKOUT4(), .CLKOUT5(), .CLKOUT6());
    BUFG u_bufg (.I(clk_mmcm), .O(clk));

    logic rst, locked_sync;
    reset_gen u_reset (.clk(clk), .locked_async(locked), .locked_sync(locked_sync), .rst(rst));

`ifdef SYNTHESIS
    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata;
`endif
    jtag_bus u_jtag (.clk(clk), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata));

    crc_core u_core (.clk(clk), .rst(rst), .locked(locked_sync), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
        .h_wdata(h_wdata), .h_rdata(h_rdata), .led(led), .sfp_tx_disable(sfp_tx_disable));
endmodule
