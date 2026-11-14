module x(input clk, input rst_n, input d, output logic q);
always_latch begin if (!rst_n) q<=0; else if (g) q<=d; end
endmodule
