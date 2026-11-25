// m12_mult27x18: 27 x 18 signed multiplier (the UltraScale+ DSP48E2 size; two DSP48E1 on 7 series), three register stages.
module m12_mult27x18 (input logic clk, input logic signed [26:0] a, input logic signed [17:0] b, output logic signed [44:0] p);
    logic signed [26:0] aq; logic signed [17:0] bq; logic signed [44:0] m;
    always_ff @(posedge clk) begin aq <= a; bq <= b; m <= aq * bq; p <= m; end
endmodule
