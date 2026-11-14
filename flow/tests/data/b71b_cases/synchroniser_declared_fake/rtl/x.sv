module myrs(input clk, rst_n, d, output logic q);
// ASYNC_REG
always @(posedge clk or negedge rst_n) if(!rst_n) q<=0; else q<=d;
endmodule
