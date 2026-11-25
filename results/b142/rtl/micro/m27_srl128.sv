// m27_srl128: 128-deep, 4-bit wide fixed delay line (four SRLC32E in a chain per bit).
module m27_srl128 (input logic clk, input logic [3:0] d, output logic [3:0] q);
    logic [3:0] sh [128];
    always_ff @(posedge clk) begin sh[0] <= d; for (int i = 1; i < 128; i++) sh[i] <= sh[i-1]; end
    assign q = sh[127];
endmodule
