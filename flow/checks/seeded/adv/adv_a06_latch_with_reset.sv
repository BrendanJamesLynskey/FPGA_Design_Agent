// adv_a06_latch_with_reset: an attack design for the sign-off netlist scan (brief 71B)
module adv_a06_latch_with_reset(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
always_latch if (!rst_n_btn) q = 1'b0; else if (clk_a) q = d;
assign p = '0;
endmodule
