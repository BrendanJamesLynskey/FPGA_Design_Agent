module x(input clk, /* rst_n, */ input d, output logic q);
logic rst_n; always @(posedge clk or negedge rst_n) if(!rst_n) q<=0; else q<=d;
endmodule
