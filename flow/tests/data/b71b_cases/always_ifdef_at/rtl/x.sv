module x(input clk, input rst_n, input d, output logic q);
always_ff
`ifdef A
@(posedge clk or negedge rst_n)
`else
@(posedge clk)
`endif
 if(!rst_n) q<=0; else q<=d;
endmodule
