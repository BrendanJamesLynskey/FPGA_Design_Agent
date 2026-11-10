// E8B: one MMCM makes 100 MHz (clk0) and 200 MHz (clk1) from the 100 MHz input: the two are synchronous.
// A 16-bit sum is launched on clk0 and captured on clk1 on every second clk1 edge (the clk1 enable follows clk0's phase).
module tex_e8b (input logic clk_in, input logic [15:0] d_in, output logic [15:0] q_out);
    logic fb, c0, c1, clk0, clk1;
    MMCME2_BASE #(.CLKIN1_PERIOD(10.0), .CLKFBOUT_MULT_F(10.0), .DIVCLK_DIVIDE(1),
                  .CLKOUT0_DIVIDE_F(10.0), .CLKOUT1_DIVIDE(5))
        mmcm (.CLKIN1(clk_in), .CLKFBIN(fb), .CLKFBOUT(fb), .CLKOUT0(c0), .CLKOUT1(c1), .RST(1'b0), .PWRDWN(1'b0),
              .CLKFBOUTB(), .CLKOUT0B(), .CLKOUT1B(), .CLKOUT2(), .CLKOUT2B(), .CLKOUT3(), .CLKOUT3B(),
              .CLKOUT4(), .CLKOUT5(), .CLKOUT6(), .LOCKED());
    BUFG b0 (.I(c0), .O(clk0));
    BUFG b1 (.I(c1), .O(clk1));
    logic [15:0] s = '0, acc = '0;
    always_ff @(posedge clk0) s <= s + d_in;
    logic ph = 1'b0;
    always_ff @(posedge clk1) begin
        ph <= ~ph;
        if (ph) acc <= acc ^ s;
    end
    assign q_out = acc;
endmodule
