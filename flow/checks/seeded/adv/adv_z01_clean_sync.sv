// adv_z01_clean_sync: an attack design for the sign-off netlist scan (brief 71B)
module adv_z01_clean_sync(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
logic r;
xpm_cdc_async_rst #(.DEST_SYNC_FF(2), .RST_ACTIVE_HIGH(0)) u (.src_arst(rst_n_btn), .dest_clk(clk_a), .dest_arst(r));
always_ff @(posedge clk_a) if (!r) q <= 1'b0; else q <= d;
assign p = '0;
endmodule
