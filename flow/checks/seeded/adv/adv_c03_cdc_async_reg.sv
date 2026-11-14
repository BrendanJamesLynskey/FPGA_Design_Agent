// adv_c03_cdc_async_reg: an attack design for the sign-off netlist scan (brief 71B)
module adv_c03_cdc_async_reg(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
logic ra;
always_ff @(posedge clk_a) ra <= ~rst_n_btn;
always_ff @(posedge clk_b or posedge ra) if (ra) q <= 1'b0; else q <= d;
assign p = '0;
endmodule
