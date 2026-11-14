// adv_a12_array: an attack design for the sign-off netlist scan (brief 71B)
module adv_a12_array(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
logic [3:0] qq;
FDCE u [3:0] (.C({4{clk_a}}), .CE({4{1'b1}}), .CLR({4{~rst_n_btn}}), .D({4{d}}), .Q(qq));
assign q = ^qq;
assign p = '0;
endmodule
