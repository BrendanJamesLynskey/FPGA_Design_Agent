module x #(parameter string S = "a, rst_n)")(input clk, d, output logic q);
logic rst_n; always @(posedge clk or negedge rst_n) if(!rst_n) q<=0; else q<=d;
endmodule
