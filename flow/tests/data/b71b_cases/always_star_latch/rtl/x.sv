module x(input clk, input rst_n, input d, output logic q);
always @(rst_n or d) if (!rst_n) q = 0; else q = d;
endmodule
