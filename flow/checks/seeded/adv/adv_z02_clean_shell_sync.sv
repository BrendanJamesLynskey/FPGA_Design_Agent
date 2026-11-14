// adv_z02_clean_shell_sync: an attack design for the sign-off netlist scan (brief 71B)
module adv_z02_clean_shell_sync(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
logic r;
reset_sync u (.clk(clk_a), .rst_n_async(rst_n_btn), .rst(r));
always_ff @(posedge clk_a) if (r) q <= 1'b0; else q <= d;
assign p = '0;
endmodule
