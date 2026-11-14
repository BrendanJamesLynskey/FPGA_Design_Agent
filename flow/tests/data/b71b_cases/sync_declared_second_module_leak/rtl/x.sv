module myrs(input clk, rst_n, d, output logic q);
(* ASYNC_REG = "TRUE" *) logic a;
always @(posedge clk or negedge rst_n) a<=d;
endmodule
module x(input clk, rst_n, d, output logic q);
always @(posedge clk or negedge rst_n) if(!rst_n) q<=0; else q<=d;
endmodule
