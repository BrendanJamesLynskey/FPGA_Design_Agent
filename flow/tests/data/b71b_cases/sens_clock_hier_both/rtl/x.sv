module x(input clk, i a, input rst_n, input d, output logic q);
always_ff @(posedge a.clk or negedge a.rst_n) q<=d;
endmodule
