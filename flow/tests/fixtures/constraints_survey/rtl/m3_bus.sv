// M3 (brief 105): a 16-bit Gray-coded pointer crossing clk_a to clk_b through 2-flop ASYNC_REG chains (the Gray-pointer half of an
// asynchronous FIFO), with filler logic so the bits are not placed together by accident.
module m3_bus #(parameter int W = 16) (
    input logic clk_a, input logic clk_b, input logic inc, input logic [W-1:0] seed, output logic [W-1:0] q_out);
    logic [W-1:0] bin = '0, gray = '0;
    wire  [W-1:0] bn = bin + {{(W-1){1'b0}}, inc};
    always_ff @(posedge clk_a) begin bin <= bn ^ (seed & {W{inc}}); gray <= (bn >> 1) ^ bn; end
    (* ASYNC_REG = "TRUE" *) logic [W-1:0] q1 = '0;
    (* ASYNC_REG = "TRUE" *) logic [W-1:0] q2 = '0;
    always_ff @(posedge clk_b) begin q1 <= gray; q2 <= q1; end
    logic [W-1:0] f1 = '0, f2 = '0;
    always_ff @(posedge clk_b) begin f1 <= f1 + q2; f2 <= f2 ^ (f1 >> 1) ^ q2; end
    always_ff @(posedge clk_b) q_out <= f1 ^ f2;
endmodule
