module lint_top (input logic clk, input logic [7:0] a, b, output logic [3:0] y);
  always_ff @(posedge clk) y <= a + b;   // truncated on purpose (ASSIGN-1)
endmodule
