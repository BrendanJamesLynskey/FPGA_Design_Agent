// Thin top: jtag_bus, MMCM (clk25 x10 -> clk_dp), core.
/* verilator lint_off PINCONNECTEMPTY */
/* verilator lint_off SYNCASYNCNET */
/* verilator lint_off UNUSEDSIGNAL */
module fir32_top (
    input  logic       clk25,
    output logic [1:0] led,
    output logic       sfp_tx_disable
);
    logic clk_fb, clk_dp_raw, clk_dp, locked, clk_fb_b;
    logic mmcm_rst = 1'b0;

    MMCME4_BASE #(.CLKFBOUT_MULT_F(40.0), .CLKIN1_PERIOD(40.0), .DIVCLK_DIVIDE(1), .CLKOUT0_DIVIDE_F(4.0)) u_mmcm (
        .CLKIN1(clk25), .CLKFBIN(clk_fb_b), .PWRDWN(1'b0), .RST(mmcm_rst),
        .CLKOUT0(clk_dp_raw), .CLKOUT0B(), .CLKOUT1(), .CLKOUT1B(), .CLKOUT2(), .CLKOUT2B(),
        .CLKOUT3(), .CLKOUT3B(), .CLKOUT4(), .CLKOUT5(), .CLKOUT6(),
        .CLKFBOUT(clk_fb), .CLKFBOUTB(), .LOCKED(locked));
    BUFG u_fb (.I(clk_fb), .O(clk_fb_b));
    BUFG u_dp (.I(clk_dp_raw), .O(clk_dp));

    logic        bus_rst, h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata;

    // jtag_bus rst: held for a few clocks at start; the core is also held in reset until the MMCM locks
    logic [3:0] por = 4'hF;
    always_ff @(posedge clk25) por <= {por[2:0], 1'b0};
    logic [1:0] locked_s = 2'b00;
    logic       bus_rst_q = 1'b1;
    always_ff @(posedge clk25) begin
        locked_s  <= {locked_s[0], locked};
        bus_rst_q <= por[3] | ~locked_s[1];
    end
    assign bus_rst = bus_rst_q;

    jtag_bus u_bus (.clk(clk25), .rst(bus_rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                    .h_wdata(h_wdata), .h_rdata(h_rdata));

    fir32_core u_core (.clk25(clk25), .clk_dp(clk_dp), .rst(bus_rst), .h_we(h_we), .h_re(h_re),
                       .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata), .led(led),
                       .sfp_tx_disable(sfp_tx_disable));
endmodule
