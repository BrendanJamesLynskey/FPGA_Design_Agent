module x(input clk, input rst_n, input d, output logic q);
xpm_cdc_single u(.src_clk(clk), .dest_clk(clk), .src_in(d), .dest_out(q));
endmodule
