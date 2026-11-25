// m09_mux16: 16-to-1 multiplexer, 16 bits wide (MUXF7 and MUXF8).
module m09_mux16 (input logic clk, input logic [15:0] d [16], input logic [3:0] s, output logic [15:0] y);
    logic [15:0] dq [16]; logic [3:0] sq;
    always_ff @(posedge clk) begin dq <= d; sq <= s; y <= dq[sq]; end
endmodule
