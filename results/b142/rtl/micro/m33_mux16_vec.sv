// m33_mux16_vec: the m09 16-to-1, 16-bit multiplexer written on one packed vector (no unpacked array, no $shiftx from an array index).
module m33_mux16_vec (input logic clk, input logic [255:0] d, input logic [3:0] s, output logic [15:0] y);
    logic [255:0] dq; logic [3:0] sq;
    always_ff @(posedge clk) begin dq <= d; sq <= s; y <= dq[sq*16 +: 16]; end
endmodule
