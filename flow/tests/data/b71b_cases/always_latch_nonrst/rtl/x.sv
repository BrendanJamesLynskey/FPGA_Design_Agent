module x(input clk, input rst_n, input d, output logic q);
always_latch if (en) q<=d;
endmodule
