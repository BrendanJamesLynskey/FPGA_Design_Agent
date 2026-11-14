module x(input clk, input rst_n, input d, output logic q);
wire ev = clk;
always @ev q<=d;
endmodule
