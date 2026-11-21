// m05_cmp32: 32-bit unsigned less-than and equality compare.
module m05_cmp32 (input logic clk, input logic [31:0] a, b, output logic lt, eq);
    logic [31:0] aq, bq;
    always_ff @(posedge clk) begin aq <= a; bq <= b; lt <= aq < bq; eq <= aq == bq; end
endmodule
