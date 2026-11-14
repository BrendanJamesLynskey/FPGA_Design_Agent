module x(input clk, input ext_rst_n, input soft_rst_n, input d, output logic q);
always @(posedge clk or negedge ext_rst_n or negedge soft_rst_n) if (!ext_rst_n || !soft_rst_n) q<=0; else q<=d;
endmodule
