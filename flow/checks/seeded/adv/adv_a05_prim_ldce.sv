// adv_a05_prim_ldce: an attack design for the sign-off netlist scan (brief 71B)
module adv_a05_prim_ldce(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
LDCE #(.INIT(1'b0)) u (.G(clk_a), .GE(1'b1), .CLR(~rst_n_btn), .D(d), .Q(q));
assign p = '0;
endmodule
