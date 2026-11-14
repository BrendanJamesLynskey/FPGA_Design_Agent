// adv_e02_oddr_async: an attack design for the sign-off netlist scan (brief 71B)
module adv_e02_oddr_async(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
ODDR #(.DDR_CLK_EDGE("SAME_EDGE"), .SRTYPE("ASYNC")) u (.C(clk_a), .CE(1'b1), .D1(d), .D2(~d), .R(~rst_n_btn), .S(1'b0), .Q(q));
assign p = '0;
endmodule
