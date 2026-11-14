// adv_a14_gated_buf: an attack design for the sign-off netlist scan (brief 71B)
module adv_a14_gated_buf(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
logic r; BUFG ub (.I(rst_n_btn), .O(r));
always_ff @(posedge clk_a or negedge r) if (!r) q <= 1'b0; else q <= d;
assign p = '0;
endmodule
