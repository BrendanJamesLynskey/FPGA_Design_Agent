// m03_add3: three-input 32-bit add (a ternary adder on Vivado: LUT6_2 pre-add plus one carry chain).
module m03_add3 (input logic clk, input logic [31:0] a, b, c, output logic [33:0] s);
    logic [31:0] aq, bq, cq;
    always_ff @(posedge clk) begin aq <= a; bq <= b; cq <= c; s <= aq + bq + cq; end
endmodule
