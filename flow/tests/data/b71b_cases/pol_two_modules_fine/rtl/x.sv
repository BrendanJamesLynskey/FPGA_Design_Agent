module x(input clk, input rst_n, input d, output logic q);
always_ff @(posedge clk) if(!rst_n) q<=0;
endmodule
module y(input clk, rst_n, output logic q);
always_ff @(posedge clk) if(rst_n) q<=0;
endmodule
