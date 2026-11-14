module x(input clk, input rst_n, input d, output logic q);
always_ff @(posedge clk or negedge rst_n iff en) if(!rst_n) q<=0; else q<=d;
endmodule
