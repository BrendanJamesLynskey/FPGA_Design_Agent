// adv_a03_prim_fdpe_inv_clk: an attack design for the sign-off netlist scan (brief 71B)
module adv_a03_prim_fdpe_inv_clk(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
FDPE_1 #(.INIT(1'b1)) u (.C(clk_a), .CE(1'b1), .PRE(~rst_n_btn), .D(d), .Q(q));
assign p = '0;
endmodule
