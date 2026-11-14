module x(input clk, input rst_n, input d, output logic q);
always_ff @(POSEDGE clk or NEGEDGE rst_n) q<=d;
endmodule
