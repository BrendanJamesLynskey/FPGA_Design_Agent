module y(input clk, rst_n, d, output reg q);
always @(posedge clk or negedge rst_n) if(!rst_n) q<=0; else q<=d;
endmodule
