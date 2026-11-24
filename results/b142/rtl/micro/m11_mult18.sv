// m11_mult18: 18 x 18 signed multiplier, operand, multiplier-output and product registers (one DSP, all registers inside).
module m11_mult18 (input logic clk, input logic signed [17:0] a, b, output logic signed [35:0] p);
    logic signed [17:0] aq, bq; logic signed [35:0] m;
    always_ff @(posedge clk) begin aq <= a; bq <= b; m <= aq * bq; p <= m; end
endmodule
