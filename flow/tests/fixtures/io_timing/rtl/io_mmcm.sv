// io_mmcm (brief 20 part B, V2): an input captured by a 125 MHz MMCM clock made from the 100 MHz board clock (a 5:4
// ratio, not an integer). The external device is clocked at 125 MHz by a clock the FPGA does not receive.
module io_mmcm (input logic CLK100MHZ, input logic [3:0] din, output logic [0:0] LED);
    logic fb, fb_bufg, c125, clk125;
    MMCME2_BASE #(.CLKIN1_PERIOD(10.0), .CLKFBOUT_MULT_F(10.0), .DIVCLK_DIVIDE(1), .CLKOUT0_DIVIDE_F(8.0))
        mmcm (.CLKIN1(CLK100MHZ), .CLKFBIN(fb_bufg), .CLKFBOUT(fb), .CLKOUT0(c125), .RST(1'b0), .PWRDWN(1'b0),
              .CLKFBOUTB(), .CLKOUT0B(), .CLKOUT1(), .CLKOUT1B(), .CLKOUT2(), .CLKOUT2B(), .CLKOUT3(), .CLKOUT3B(),
              .CLKOUT4(), .CLKOUT5(), .CLKOUT6(), .LOCKED());
    BUFG bfb (.I(fb), .O(fb_bufg));     // feedback through a BUFG: the MMCM then cancels the clock tree's delay
    BUFG b (.I(c125), .O(clk125));
    (* IOB = "true" *) logic [3:0] dq = '0;
    logic [3:0] acc = '0;
    logic par = 1'b0;
    always_ff @(posedge clk125) begin
        dq  <= din;
        acc <= acc + dq;
        par <= ^acc;
    end
    assign LED[0] = par;
endmodule
