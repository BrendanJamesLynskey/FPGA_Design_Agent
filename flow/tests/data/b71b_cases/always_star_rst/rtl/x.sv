module x(input clk, input rst_n, input d, output logic q);
always @* if (!rst_n) q = 0; else q = d;
endmodule
