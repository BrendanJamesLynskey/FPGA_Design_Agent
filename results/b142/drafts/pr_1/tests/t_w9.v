module t(input [8:0] a, b, input s, c, output [9:0] y, output lt, eq, output [8:0] d);
  assign y = s ? {1'b0,a} - {1'b0,b} - c : {1'b0,a} + {1'b0,b} + c;
  assign lt = a < b;  assign eq = a == b;  assign d = a - b;
endmodule
