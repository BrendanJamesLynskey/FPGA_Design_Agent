module x(input clk, input rst_n, input d, output logic q);
always_ff @(negedge rst_n or posedge clk) q<=d;
endmodule
