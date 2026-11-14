module x #(parameter int W=1, parameter bit [1:0] Z=2'b01)(input clk, rst_n, d, output logic q);
always @(posedge clk or negedge rst_n) if(!rst_n) q<=0; else q<=d;
endmodule
