// m13_preadd: (a + d) * b with the pre-adder (DSP48E2 AD path: 27 bits, so a and d are 26-bit and the sum fits), registers throughout.
module m13_preadd (input logic clk, input logic signed [25:0] a, d, input logic signed [17:0] b, output logic signed [44:0] p);
    logic signed [25:0] aq, dq; logic signed [17:0] bq; logic signed [26:0] ad; logic signed [44:0] m;
    always_ff @(posedge clk) begin aq <= a; dq <= d; bq <= b; ad <= aq + dq; m <= ad * bq; p <= m; end
endmodule
