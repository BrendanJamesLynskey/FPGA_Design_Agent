// m25_srl32: 32-deep, 16-bit wide shift register with an enable (SRLC32E), no reset.
module m25_srl32 (input logic clk, input logic en, input logic [15:0] d, output logic [15:0] q);
    logic [15:0] sh [32];
    always_ff @(posedge clk) if (en) begin sh[0] <= d; for (int i = 1; i < 32; i++) sh[i] <= sh[i-1]; end
    assign q = sh[31];
endmodule
