module x(input clk, input rst_n, input d, output logic q);
always @(clk or rst_n) if (!rst_n) q <= 0; else if (clk) q<=d;
endmodule
