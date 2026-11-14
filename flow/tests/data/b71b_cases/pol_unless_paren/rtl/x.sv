module x(input clk, input rst_n, input d, output logic q);
always_ff @(posedge clk) if (rst_n == 1'b0) q<=0;
always_ff @(posedge clk) if (rst_n && en) q<=d;
endmodule
