// Thin top: jtag_bus, MMCM (25 MHz x 10 = 250 MHz), reset generator and the register core.
/* verilator lint_off SYNCASYNCNET */
/* verilator lint_off UNUSEDSIGNAL */
module fir32_top (
    input  logic       clk25,
    output logic [1:0] led,
    output logic       sfp_tx_disable
);
    // internal register bus (no pins)
    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata;
    // reset generator: held a few clocks after start, and while the MMCM is unlocked
    logic [3:0] rst_cnt = 4'd0;
    logic       rst_q   = 1'b1;
    wire        locked, locked25;
    logic       rst25   = 1'b1;   // registered: it drives an asynchronous-reset synchroniser
    always_ff @(posedge clk25) begin
        rst25 <= rst_q | ~locked25;
        if (rst_cnt != 4'd15) rst_cnt <= rst_cnt + 4'd1;
        rst_q <= (rst_cnt != 4'd15);
    end

    wire fb, clk_mmcm, clk_dsp;
    MMCME4_BASE #(.CLKIN1_PERIOD(40.0), .DIVCLK_DIVIDE(1), .CLKFBOUT_MULT_F(40.0), .CLKOUT0_DIVIDE_F(4.0)) u_mmcm (
        .CLKIN1(clk25), .CLKFBIN(fb), .RST(1'b0), .PWRDWN(1'b0),
        .CLKOUT0(clk_mmcm), .CLKFBOUT(fb), .LOCKED(locked));
    BUFG u_bufg (.I(clk_mmcm), .O(clk_dsp));

    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_lock (
        .src_clk(clk_mmcm), .src_in(locked), .dest_clk(clk25), .dest_out(locked25));

    wire [1:0]  led_core;
    jtag_bus u_bus (.clk(clk25), .rst(rst25), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                    .h_wdata(h_wdata), .h_rdata(h_rdata));

    fir32_core u_core (
        .clk25(clk25), .clk_dsp(clk_dsp), .rst(rst25),
        .h_we(h_we), .h_re(h_re), .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata),
        .led(led_core), .sfp_tx_disable(sfp_tx_disable));
    assign led = {locked25, led_core[0]};
endmodule
