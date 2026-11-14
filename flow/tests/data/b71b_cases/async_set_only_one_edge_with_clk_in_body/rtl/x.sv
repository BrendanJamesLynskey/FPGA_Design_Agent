module x(input clk, input rst_n, input d, output logic q);
always @(negedge rst_n) if(!rst_n) q<=1;
always_ff @(posedge clk) if (rst_n) q<=d;
endmodule
