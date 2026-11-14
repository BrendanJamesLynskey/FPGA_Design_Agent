interface i; logic clk, rst_n; modport m(input clk); endinterface
module x(i.m a, input rst_n, d, output logic q);
always @(posedge a.clk or negedge rst_n) if(!rst_n) q<=0; else q<=d;
endmodule
