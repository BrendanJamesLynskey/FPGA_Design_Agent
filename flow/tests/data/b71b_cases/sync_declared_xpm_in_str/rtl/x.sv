module x(input clk, rst_n, d, output logic q);
localparam s="xpm_cdc_";
always_ff @(posedge clk or negedge rst_n) if(!rst_n) q<=0; else q<=d;
endmodule
