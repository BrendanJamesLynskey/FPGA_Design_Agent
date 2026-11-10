// E3: the same multiply with no enable: every register loads on every clock (CE tied high), so a multicycle is false.
(* use_dsp = "no" *)
module tex_e3 (input logic clk, input logic [15:0] a_in, input logic [15:0] b_in, output logic [31:0] p_out);
    logic [15:0] a = '0, b = '0;
    logic [31:0] p = '0;
    always_ff @(posedge clk) begin
        a <= a_in;
        b <= b_in;
        p <= a * b;
    end
    assign p_out = p;
endmodule
