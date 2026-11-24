// m01_add32: 32-bit add, registered in and out.
module m01_add32 (input logic clk, input logic [31:0] a, b, output logic [31:0] s);
    logic [31:0] aq, bq;
    always_ff @(posedge clk) begin aq <= a; bq <= b; s <= aq + bq; end
endmodule
