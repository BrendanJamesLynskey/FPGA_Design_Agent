checker c(input clk, rst_n, d);
always_ff @(posedge clk or negedge rst_n) if (!rst_n) x<=0; else x<=d;
endchecker
module x(input clk,rst_n,d,output logic q); endmodule
