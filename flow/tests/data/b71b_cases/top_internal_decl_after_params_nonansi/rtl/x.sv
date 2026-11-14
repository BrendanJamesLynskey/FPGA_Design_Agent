module x #(parameter rst_n = 1)(clk, d, q);
input clk,d; output reg q; wire rst_n2;
always @(posedge clk or negedge rst_n) if(!rst_n) q<=0; else q<=d;
endmodule
