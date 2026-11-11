// io_u (brief 20 part B, U1-U8): the clock-uncertainty top. CLK100MHZ -> MMCM (VCO 1000 MHz) -> clk200 (CLKOUT0, /5)
// and clk100 (CLKOUT1, /10). Paths: a 24-bit add on clk200 (rising to rising), a half-period path on clk200 (rising
// launch, falling capture), and a clk100 -> clk200 crossing (synchronous: same MMCM). Switches in, LEDs out (slow ports).
(* use_dsp = "no" *)
module io_u (input logic CLK100MHZ, input logic [7:0] SW, output logic [2:0] LED);
    logic fb, c200, c100, clk200, clk100;
    MMCME2_BASE #(.CLKIN1_PERIOD(10.0), .CLKFBOUT_MULT_F(10.0), .DIVCLK_DIVIDE(1),
                  .CLKOUT0_DIVIDE_F(5.0), .CLKOUT1_DIVIDE(10))
        mmcm (.CLKIN1(CLK100MHZ), .CLKFBIN(fb), .CLKFBOUT(fb), .CLKOUT0(c200), .CLKOUT1(c100), .RST(1'b0), .PWRDWN(1'b0),
              .CLKFBOUTB(), .CLKOUT0B(), .CLKOUT1B(), .CLKOUT2(), .CLKOUT2B(), .CLKOUT3(), .CLKOUT3B(),
              .CLKOUT4(), .CLKOUT5(), .CLKOUT6(), .LOCKED());
    BUFG b0 (.I(c200), .O(clk200));
    BUFG b1 (.I(c100), .O(clk100));
    (* ASYNC_REG = "true" *) logic [7:0] sw_a = '0, sw_b = '0;
    logic [23:0] a = '0, b = '0, s = '0;
    logic [7:0] slow = '0, x = '0;
    logic hp = 1'b0, hq = 1'b0;
    always_ff @(posedge clk100) begin
        sw_a <= SW;
        sw_b <= sw_a;
        slow <= slow + sw_b;
    end
    always_ff @(posedge clk200) begin
        a  <= a + {16'd0, sw_b};
        b  <= {b[22:0], a[23]};
        s  <= a + b;                 // the full-period path: 24-bit add
        x  <= slow ^ s[7:0];         // the clk100 -> clk200 crossing
        hp <= ^s[23:16];
    end
    always_ff @(negedge clk200) hq <= hp ^ s[3];   // the half-period path (rising launch, falling capture)
    assign LED = {hq, ^x, s[23]};
endmodule
