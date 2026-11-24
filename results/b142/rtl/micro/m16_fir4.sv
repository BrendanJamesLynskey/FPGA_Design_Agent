// m16_fir4: 4-tap transposed FIR, coefficients as inputs; the sums chain through the DSP cascade (PCOUT to PCIN).
module m16_fir4 (input logic clk, input logic signed [15:0] x, input logic signed [15:0] c [4], output logic signed [39:0] y);
    logic signed [15:0] xq; logic signed [15:0] cq [4];
    logic signed [31:0] m [4]; logic signed [39:0] s [4];
    always_ff @(posedge clk) begin
        xq <= x; cq <= c;
        for (int i = 0; i < 4; i++) m[i] <= xq * cq[i];
        s[0] <= 40'(m[0]);
        for (int i = 1; i < 4; i++) s[i] <= s[i-1] + 40'(m[i]);
        y <= s[3];
    end
endmodule
