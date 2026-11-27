// Board top: jtag_bus, MMCM (25 -> 250 MHz), reset generator and the register core.
/* verilator lint_off PINCONNECTEMPTY */
/* verilator lint_off UNUSEDSIGNAL */
module fir_top (
    input  logic       clk_25,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic       clk25,
    output logic [1:0] led,
    output logic       sfp_tx_disable
);
    // ---- clk25 reset generator: held for a few clocks at start ----
    logic [3:0] rst_cnt = 4'd0;
    logic       rst = 1'b1;
    always_ff @(posedge clk_25) begin
        if (rst_cnt != 4'd15) rst_cnt <= rst_cnt + 4'd1;
        rst <= (rst_cnt != 4'd15);
    end

    // ---- MMCM: VCO 25*40 = 1000 MHz, /4 = 250 MHz ----
    logic clk_fb, clk_dp_raw, clk_dp, locked;
    MMCME4_BASE #(
        .BANDWIDTH("OPTIMIZED"), .CLKFBOUT_MULT_F(40.0), .CLKFBOUT_PHASE(0.0), .CLKIN1_PERIOD(40.0),
        .CLKOUT0_DIVIDE_F(4.0), .CLKOUT0_DUTY_CYCLE(0.5), .CLKOUT0_PHASE(0.0), .DIVCLK_DIVIDE(1),
        .REF_JITTER1(0.0), .STARTUP_WAIT("FALSE")
    ) u_mmcm (
        .CLKFBOUT(clk_fb), .CLKFBOUTB(), .CLKOUT0(clk_dp_raw), .CLKOUT0B(), .LOCKED(locked),
        .CLKFBIN(clk_fb), .CLKIN1(clk_25), .PWRDWN(1'b0), .RST(1'b0));
    BUFG u_bufg (.O(clk_dp), .I(clk_dp_raw));

    // ---- host register bus ----
    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata;
    jtag_bus u_bus (.clk(clk_25), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                    .h_wdata(h_wdata), .h_rdata(h_rdata));

    fir_core u_core (.clk(clk_25), .clk_dp(clk_dp), .rst(rst), .dp_locked(locked),
                     .h_we(h_we), .h_re(h_re), .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata),
                     .led(led), .sfp_tx_disable(sfp_tx_disable));
endmodule
