// E6B: a 16x16 multiply in LUTs; operands and product load only on a 1-in-2 enable, so a -> p has two clocks.
(* use_dsp = "no" *)
module tex_e6b (input logic clk, input logic [15:0] a_in, input logic [15:0] b_in, output logic [31:0] p_out);
    logic en = 1'b0;
    logic [15:0] a = '0, b = '0;
    logic [31:0] p = '0;
    always_ff @(posedge clk) begin
        en <= ~en;
        if (en) begin
            a <= a_in;
            b <= b_in;
            p <= a * b;
        end
    end
    assign p_out = p;
endmodule
