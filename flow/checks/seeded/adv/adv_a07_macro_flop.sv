// adv_a07_macro_flop: an attack design for the sign-off netlist scan (brief 71B)
module adv_a07_macro_flop(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
`define FF(C,R,Q,D) always_ff @(posedge C or negedge R) if (!R) Q <= 1'b0; else Q <= D;
`FF(clk_a, rst_n_btn, q, d)
assign p = '0;
endmodule
