// m08_mux8: 8-to-1 multiplexer, 16 bits wide (one MUXF7 level on Vivado).
module m08_mux8 (input logic clk, input logic [15:0] d [8], input logic [2:0] s, output logic [15:0] y);
    logic [15:0] dq [8]; logic [2:0] sq;
    always_ff @(posedge clk) begin dq <= d; sq <= s; y <= dq[sq]; end
endmodule
