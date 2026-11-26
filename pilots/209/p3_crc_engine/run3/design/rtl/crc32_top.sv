// crc32_top: MMCM (25 -> 100 MHz), reset generator, jtag_bus and crc32_core.
/* verilator lint_off DECLFILENAME */
/* verilator lint_off PINCONNECTEMPTY */
module crc32_top (
    input  logic       clk_25,
    output logic [1:0] led,
    output logic       sfp_tx_disable
);
    logic clk25_b, fb, fb_b, clk_mmcm, clk, locked, rst, locked_s;
    logic [31:0] build_word;
    logic        jb_we, jb_re;
    logic [11:0] jb_addr;
    logic [31:0] jb_wdata, jb_rdata;

    BUFG u_bufg_in (.I(clk_25), .O(clk25_b));

    // VCO = 25 * 40 = 1000 MHz, CLKOUT0 = 1000/10 = 100 MHz
    MMCME4_BASE #(
        .CLKIN1_PERIOD(40.0), .CLKFBOUT_MULT_F(40.0), .DIVCLK_DIVIDE(1), .CLKOUT0_DIVIDE_F(10.0)
    ) u_mmcm (
        .CLKIN1(clk25_b), .CLKFBIN(fb_b), .CLKFBOUT(fb), .CLKOUT0(clk_mmcm), .LOCKED(locked),
        .PWRDWN(1'b0), .RST(1'b0),
        .CLKFBOUTB(), .CLKOUT0B(), .CLKOUT1(), .CLKOUT1B(), .CLKOUT2(), .CLKOUT2B(),
        .CLKOUT3(), .CLKOUT3B(), .CLKOUT4(), .CLKOUT5(), .CLKOUT6()
    );
    BUFG u_bufg_fb  (.I(fb), .O(fb_b));
    BUFG u_bufg_clk (.I(clk_mmcm), .O(clk));

    reset_gen #(.HOLD(8)) u_rst (.clk(clk), .locked(locked), .rst(rst));

    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(0)) u_lock_led (
        .src_clk(1'b0), .src_in(locked), .dest_clk(clk), .dest_out(locked_s));

`ifdef SYNTHESIS
    USR_ACCESSE2 u_usr (.CFGCLK(), .DATA(build_word), .DATAVALID());
`else
    assign build_word = 32'h0;
`endif

    jtag_bus u_jtag (.clk(clk), .rst(rst), .h_we(jb_we), .h_re(jb_re), .h_addr(jb_addr),
                     .h_wdata(jb_wdata), .h_rdata(jb_rdata));

    crc32_core u_core (.clk(clk), .rst(rst), .locked(locked_s), .build_word(build_word),
                       .h_we(jb_we), .h_re(jb_re), .h_addr(jb_addr), .h_wdata(jb_wdata),
                       .h_rdata(jb_rdata), .led(led), .sfp_tx_disable(sfp_tx_disable));
endmodule

// Reset generator: asynchronous assert on !locked, synchronous release, held HOLD clk.
module reset_gen #(parameter int HOLD = 8) (
    input  logic clk,
    input  logic locked,
    output logic rst
);
    logic rst_sync;
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(0)) u_ars (
        .src_arst(locked), .dest_clk(clk), .dest_arst(rst_sync));
    logic [$clog2(HOLD+1)-1:0] cnt;
    always_ff @(posedge clk) begin
        if (rst_sync) begin cnt <= '0; rst <= 1'b1; end
        else if (cnt == HOLD[$clog2(HOLD+1)-1:0]) rst <= 1'b0;
        else cnt <= cnt + 1'b1;
    end
endmodule
