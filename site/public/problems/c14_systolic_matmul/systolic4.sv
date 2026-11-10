// Part 14 lesson 4 exercise: a 4 x 4 weight-stationary systolic array computing C = A x W for signed 8-bit A and W (C[m][j] = sum over i of A[m][i] * W[i][j]).
//
// PE (i, j) holds the weight W[i][j]. Activations travel along a row (left to right, one register per PE); partial sums travel down a column (top to bottom, one
// register per PE). In every PE, each clock:   a_reg <= a_left;   p_reg <= p_above + a_left * W[i][j]   (row 0 has p_above = 0, column 0 has a_left = a_in[i]).
//
// Weights: with w_load = 1 for one clock, all 16 weights are taken from w_in: W[i][j] = w_in[(4*i + j)*8 +: 8]. Reset (rst_n low, synchronous) clears every a_reg and
// p_reg to zero. a_in[i*8 +: 8] is the activation entering row i; c_out[j*32 +: 32] is the signed sum leaving the bottom of column j (the p_reg of PE (3, j)).
//
// Timing: if A[m][i] is applied on a_in[i] in clock cycle m + i (sampled at the rising edge that ends that cycle; the rows are skewed by one cycle each), then
// c_out[j] holds C[m][j] after the rising edge that ends cycle m + j + 3, so it can be read during cycle m + j + 4 (a cycle starts at a rising edge).
// A zero on a_in is a bubble (it adds nothing). Only one multiply-accumulate per PE per clock: after the pipeline fills, all 16 multipliers work every clock.
module systolic4 (
    input  logic          clk,
    input  logic          rst_n,
    input  logic          w_load,
    input  logic [127:0]  w_in,
    input  logic [31:0]   a_in,
    output logic [127:0]  c_out
);
    logic signed [7:0]  wt   [0:3][0:3];
    logic signed [7:0]  a_r  [0:3][0:3];
    logic signed [31:0] p_r  [0:3][0:3];

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            for (int i = 0; i < 4; i++)
                for (int j = 0; j < 4; j++) begin
                    a_r[i][j] <= '0;
                    p_r[i][j] <= '0;
                    wt[i][j]  <= '0;
                end
        end else begin
            for (int i = 0; i < 4; i++)
                for (int j = 0; j < 4; j++) begin
                    if (w_load) wt[i][j] <= w_in[(4*i + j)*8 +: 8];
                    a_r[i][j] <= (j == 0) ? $signed(a_in[i*8 +: 8]) : a_r[i][j-1];
                    p_r[i][j] <= ((i == 0) ? 32'sd0 : p_r[i-1][j])
                                 + ((j == 0) ? $signed(a_in[i*8 +: 8]) : a_r[i][j-1]) * wt[i][j];
                end
        end
    end
    always_comb
        for (int j = 0; j < 4; j++) c_out[j*32 +: 32] = p_r[3][j];
endmodule
