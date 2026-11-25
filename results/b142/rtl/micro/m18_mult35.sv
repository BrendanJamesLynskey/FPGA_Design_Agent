// m18_mult35: 35 x 35 signed multiplier (four DSP48E2 with partial-product adds), three register stages.
module m18_mult35 (input logic clk, input logic signed [34:0] a, b, output logic signed [69:0] p);
    logic signed [34:0] aq, bq; logic signed [69:0] m;
    always_ff @(posedge clk) begin aq <= a; bq <= b; m <= aq * bq; p <= m; end
endmodule
