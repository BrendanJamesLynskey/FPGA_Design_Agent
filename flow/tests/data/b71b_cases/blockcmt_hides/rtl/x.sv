module x(input clk, input rst_n, input d, output logic q);
/* always_ff @(posedge clk or negedge rst_n) */
always_ff @(posedge clk) q<=d;
endmodule
