module x(input clk, input [1:0] rst_n, input d, output logic q);
always_ff @(posedge clk or negedge rst_n[I]) q<=d;
endmodule
