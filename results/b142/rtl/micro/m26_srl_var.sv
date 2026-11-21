// m26_srl_var: 32-deep, 8-bit wide shift register with a runtime tap (SRLC32E address).
module m26_srl_var (input logic clk, input logic [7:0] d, input logic [4:0] tap, output logic [7:0] q);
    logic [7:0] sh [32];
    always_ff @(posedge clk) begin sh[0] <= d; for (int i = 1; i < 32; i++) sh[i] <= sh[i-1]; q <= sh[tap]; end
endmodule
