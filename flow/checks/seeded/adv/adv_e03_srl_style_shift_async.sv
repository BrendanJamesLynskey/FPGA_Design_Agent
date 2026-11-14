// adv_e03_srl_style_shift_async: an attack design for the sign-off netlist scan (brief 71B)
module adv_e03_srl_style_shift_async(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
logic [7:0] sh;
always_ff @(posedge clk_a or negedge rst_n_btn) if (!rst_n_btn) sh <= '0; else sh <= {sh[6:0], d};
assign q = sh[7];
assign p = '0;
endmodule
