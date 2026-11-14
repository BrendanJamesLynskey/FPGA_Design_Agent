`ifndef FF_SVH
`define FF_SVH
// body
always_ff @(posedge clk or negedge rst_n) if(!rst_n) q<=0; else q<=d;
`endif
