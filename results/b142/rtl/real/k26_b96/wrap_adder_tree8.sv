// wrap_adder_tree8: an input register and an output register around the combinational tree.
module ooc_wrap (input wire logic clk, input wire logic [63:0] a, output logic [10:0] s);
    logic [63:0] a_q;
    logic [10:0] s_w;
    always_ff @(posedge clk) begin
        a_q <= a;
        s   <= s_w;
    end
    adder_tree8 u_blk (.a(a_q), .s(s_w));
endmodule
