// adv_a11_user_module_named_reset_sync: an attack design for the sign-off netlist scan (brief 71B)
module reset_sync(input logic clk, input logic rst_n, input logic d, output logic q);
always_ff @(posedge clk or negedge rst_n) if (!rst_n) q <= 1'b0; else q <= d;
endmodule
module adv_a11_user_module_named_reset_sync(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
reset_sync u (.clk(clk_a), .rst_n(rst_n_btn), .d(d), .q(q));
assign p = '0;
endmodule
