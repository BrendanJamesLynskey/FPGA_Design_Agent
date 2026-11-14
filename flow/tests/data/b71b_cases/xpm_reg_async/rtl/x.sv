module x(input clk, input rst_n, input d, output logic q);
xpm_cdc_async_rst #(.DEST_SYNC_FF(4)) u(.dest_clk(clk), .dest_arst(), .src_arst(rst_n));
endmodule
