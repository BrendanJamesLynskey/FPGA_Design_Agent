`define M module
`M x(input clk, rst_n, d, output logic q);
always_ff @(posedge clk or negedge rst_n) if(!rst_n) q<=0; else q<=d;
endmodule
