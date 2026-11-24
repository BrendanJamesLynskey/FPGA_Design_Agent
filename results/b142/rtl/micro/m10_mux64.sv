// m10_mux64: 64-to-1 multiplexer, 8 bits wide (needs more than MUXF8).
module m10_mux64 (input logic clk, input logic [7:0] d [64], input logic [5:0] s, output logic [7:0] y);
    logic [7:0] dq [64]; logic [5:0] sq;
    always_ff @(posedge clk) begin dq <= d; sq <= s; y <= dq[sq]; end
endmodule
