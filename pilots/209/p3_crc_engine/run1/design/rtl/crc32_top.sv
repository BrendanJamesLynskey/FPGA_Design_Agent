// Board top: MMCM 25 -> 125 MHz, reset generator, jtag_bus and crc32_core.
module crc32_top (
    input  logic       clk_25,
    output logic [1:0] led,
    output logic       sfp_tx_disable,
    // spec-declared internal register-port names, exposed as unconstrained-free mirrors
    output logic       h_we,
    output logic       h_re,
    output logic [11:0] h_addr,
    output logic [31:0] h_wdata,
    output logic [31:0] h_rdata
);
    logic clk_fb, clk_mmcm, clk, locked, rst;
    MMCME4_BASE #(.CLKIN1_PERIOD(40.0), .DIVCLK_DIVIDE(1), .CLKFBOUT_MULT_F(40.0),
                  .CLKOUT0_DIVIDE_F(8.0)) u_mmcm (
        .CLKIN1(clk_25), .CLKFBIN(clk_fb), .CLKFBOUT(clk_fb), .CLKOUT0(clk_mmcm),
        .LOCKED(locked), .PWRDWN(1'b0), .RST(1'b0));
    BUFG u_bufg (.I(clk_mmcm), .O(clk));

    crc32_rst_gen u_rst_gen (.clk(clk), .locked(locked), .rst(rst));

    jtag_bus u_jtag (.clk(clk), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                     .h_wdata(h_wdata), .h_rdata(h_rdata));

    crc32_core u_core (.clk(clk), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                       .h_wdata(h_wdata), .h_rdata(h_rdata), .locked(locked), .led(led));

    assign sfp_tx_disable = 1'b1;
endmodule
