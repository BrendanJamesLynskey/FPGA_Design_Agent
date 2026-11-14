// adv_a08_async_set: an attack design for the sign-off netlist scan (brief 71B)
module adv_a08_async_set(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
always_ff @(posedge clk_a or negedge rst_n_btn) if (!rst_n_btn) q <= 1'b1; else q <= d;
assign p = '0;
endmodule
