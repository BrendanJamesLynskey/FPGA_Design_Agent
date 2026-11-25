// brief 204a fixture: a cascaded global buffer (BUFG driving a BUFG) and a local clock (a fabric counter's output used as a clock)
module toy_clk (input clk, input [7:0] d, output reg [7:0] q1, output reg [7:0] q2, output reg [7:0] q3);
  wire c0, c1;
  BUFG b0 (.I(clk), .O(c0));
  BUFG b1 (.I(c0), .O(c1));
  reg [3:0] div = 0;
  always @(posedge c0) div <= div + 1;
  always @(posedge c0) q1 <= d;
  always @(posedge c1) q2 <= q1;
  always @(posedge div[3]) q3 <= q2;
endmodule
