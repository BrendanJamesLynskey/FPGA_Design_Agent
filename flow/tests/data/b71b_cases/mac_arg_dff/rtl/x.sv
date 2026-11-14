`define DFFAR(q,d,c,r) always_ff @(posedge c or negedge r) if(!r) q<=0; else q<=d;
module x(input clk, input rst_n, input d, output logic q);
`DFFAR(q,d,clk,rst_n)
endmodule
