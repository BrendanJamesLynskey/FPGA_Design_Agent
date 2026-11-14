module x(input clk, input rst_n, input d, output logic q);
wire arst = ~rst_n;
always_ff @(posedge clk or posedge arst) if(arst) q<=0; else q<=d;
endmodule
