// fir32_top: board top. Power-on reset, MMCM 25 -> 250 MHz, jtag_bus and the register core.
module fir32_top (
    input  logic       clk_25,
    output logic [1:0] led,
    output logic       sfp_tx_disable
);
    logic rst, clk_fb, clk_dsp_raw, clk_dsp, locked, clk_fb_b;
    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata;

    rst_gen #(.RST_HOLD_CYCLES(16)) u_rst (.clk(clk_25), .locked(locked), .rst(rst));

    MMCME4_BASE #(.CLKIN1_PERIOD(40.0), .CLKFBOUT_MULT_F(40.0), .DIVCLK_DIVIDE(1), .CLKOUT0_DIVIDE_F(4.0)) u_mmcm (
        .CLKIN1(clk_25), .CLKFBIN(clk_fb_b), .CLKFBOUT(clk_fb), .CLKOUT0(clk_dsp_raw),
        .LOCKED(locked), .RST(1'b0), .PWRDWN(1'b0));
    BUFG u_fb  (.I(clk_fb), .O(clk_fb_b));
    BUFG u_dsp (.I(clk_dsp_raw), .O(clk_dsp));

    jtag_bus u_bus (.clk(clk_25), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                    .h_wdata(h_wdata), .h_rdata(h_rdata));

    fir32_core u_core (.clk(clk_25), .clk_dsp(clk_dsp), .rst(rst), .h_we(h_we), .h_re(h_re),
                       .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata), .led(led));

    assign sfp_tx_disable = 1'b1;
endmodule
