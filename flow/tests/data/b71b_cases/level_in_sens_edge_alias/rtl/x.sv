module x(input clk, input rst_n, input d, output logic q);
always_ff @(posedge clk or posedge rst) if(rst) q<=0; else q<=d;
endmodule
