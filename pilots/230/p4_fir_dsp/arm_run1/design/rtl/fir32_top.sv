// Board top: MMCM (25 MHz x10 = 250 MHz), reset generator, jtag_bus, register core.
module fir32_top (
    input  logic       clk_25,
    output logic [1:0] led,
    output logic       sfp_tx_disable
);
    logic clk_fb, clk_dp_raw, clk_dp, locked, rst;

    MMCME4_ADV #(
        .BANDWIDTH("OPTIMIZED"), .CLKFBOUT_MULT_F(40.0), .CLKIN1_PERIOD(40.0),
        .CLKOUT0_DIVIDE_F(4.0), .DIVCLK_DIVIDE(1)
    ) u_mmcm (
        .CLKIN1(clk_25), .CLKINSEL(1'b1), .CLKFBIN(clk_fb), .CLKFBOUT(clk_fb),
        .CLKOUT0(clk_dp_raw), .LOCKED(locked), .PWRDWN(1'b0), .RST(1'b0));
    BUFG u_bufg (.I(clk_dp_raw), .O(clk_dp));

    reset_gen #(.RESET_CYCLES(16)) u_rst (.clk(clk_25), .locked(locked), .rst(rst));

    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata, build_word;
    jtag_bus u_bus (.clk(clk_25), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                    .h_wdata(h_wdata), .h_rdata(h_rdata));

    /* verilator lint_off PINCONNECTEMPTY */
    USR_ACCESSE2 u_usr (.CFGCLK(), .DATA(build_word), .DATAVALID());
    /* verilator lint_on PINCONNECTEMPTY */

    fir32_core u_core (
        .clk_25(clk_25), .clk_dp(clk_dp), .rst(rst),
        .h_we(h_we), .h_re(h_re), .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata),
        .build_word(build_word), .led(led), .sfp_tx_disable(sfp_tx_disable));
endmodule
