module top_s1_lowvco(input clk, input din, output reg dout);
  wire fb, fbb, c0, c0b, lk;
  MMCME2_BASE #(.CLKIN1_PERIOD(10.0), .DIVCLK_DIVIDE(5), .CLKFBOUT_MULT_F(30.0), .CLKOUT0_DIVIDE_F(12.0)) mm
    (.CLKIN1(clk), .CLKFBIN(fbb), .CLKFBOUT(fb), .CLKOUT0(c0), .LOCKED(lk), .PWRDWN(1'b0), .RST(1'b0));
  BUFG b1(.I(fb), .O(fbb));
  BUFG b2(.I(c0), .O(c0b));
  reg q = 0;
  always @(posedge c0b) begin q <= din; dout <= q; end
endmodule
