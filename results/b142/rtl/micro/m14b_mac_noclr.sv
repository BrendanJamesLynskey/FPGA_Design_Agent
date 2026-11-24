// m14b_mac_noclr: multiply-accumulate with no clear, acc <= acc + a*b (the plain DSP48E2 P-register feedback).
module m14b_mac_noclr (input logic clk, input logic signed [17:0] a, b, output logic signed [47:0] acc);
    logic signed [17:0] aq, bq; logic signed [35:0] m;
    always_ff @(posedge clk) begin aq <= a; bq <= b; m <= aq * bq; acc <= acc + m; end
endmodule
