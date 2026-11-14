module x(input clk, rst_n, d, output logic q); sub s(.*); endmodule
module sub(input clk, rst_n, d, output logic q);
always @(posedge clk or negedge rst_n) if(!rst_n) q<=0; else q<=d;
endmodule
