module x(input clk, input rst_n, input d, output logic q);
always_ff @(posedge clk or negedge go) if(!go) q<=0; else q<=d;
endmodule
