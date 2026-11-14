`ifdef A
module x(input clk, rst_n, d, output logic q);
`else
module x(input clk, rst_n, d, output logic q);
`endif
always_ff @(posedge clk or negedge rst_n) if(!rst_n) q<=0; else q<=d;
endmodule
