// m19_mult_nolat: 24 x 24 unsigned product, only an input and an output register (the tool chooses how many DSP and where registers go).
module m19_mult_nolat (input logic clk, input logic [23:0] a, b, output logic [47:0] p);
    logic [23:0] aq, bq;
    always_ff @(posedge clk) begin aq <= a; bq <= b; p <= aq * bq; end
endmodule
