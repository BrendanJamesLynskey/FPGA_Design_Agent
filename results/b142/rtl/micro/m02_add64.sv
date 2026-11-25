// m02_add64: 64-bit add, registered in and out.
module m02_add64 (input logic clk, input logic [63:0] a, b, output logic [63:0] s);
    logic [63:0] aq, bq;
    always_ff @(posedge clk) begin aq <= a; bq <= b; s <= aq + bq; end
endmodule
