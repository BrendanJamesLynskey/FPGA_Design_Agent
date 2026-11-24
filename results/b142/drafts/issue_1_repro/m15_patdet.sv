// m15_patdet: accumulator that flags when it reaches a constant (DSP48E2 pattern detector).
module m15_patdet (input logic clk, input logic signed [17:0] a, b, output logic hit);
    logic signed [17:0] aq, bq; logic signed [35:0] m; logic signed [47:0] acc;
    always_ff @(posedge clk) begin
        aq <= a; bq <= b; m <= aq * bq; acc <= acc + m;
        hit <= (acc == 48'sh0000_1234_5678);
    end
endmodule
