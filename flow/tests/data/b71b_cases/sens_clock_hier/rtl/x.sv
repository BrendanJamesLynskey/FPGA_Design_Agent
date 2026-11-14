module x(input clk, i a, input rst_n, input d, output logic q);
always_ff @(posedge a.clk or negedge rst_n) if(!rst_n) q<=0; else q<=d;
endmodule
