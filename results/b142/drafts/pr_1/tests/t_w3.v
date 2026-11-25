module t(input [2:0] a, b, input s, c, output [3:0] y, output lt, eq, output [2:0] d);
  assign y = s ? {1'b0,a} - {1'b0,b} - c : {1'b0,a} + {1'b0,b} + c;
  assign lt = a < b;  assign eq = a == b;  assign d = a - b;
endmodule
