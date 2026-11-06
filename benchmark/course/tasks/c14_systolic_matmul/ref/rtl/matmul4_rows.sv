// P14-3 reference: a row-in, row-out 4 x 4 matrix multiplier. The weight-stationary array of the course (systolic4.sv) with the input rows skewed (element i delayed by i clocks) and the
// output columns de-skewed (column j delayed by 3 - j clocks), so that C[m][*] appears together, 7 clocks after the edge that sampled A[m][*]. row_valid has no gaps requirement: a new row every clock.
module matmul4_rows (
    input  logic          clk,
    input  logic          rst_n,
    input  logic          w_load,
    input  logic [127:0]  w_in,             // W[i][j] = w_in[(4*i + j)*8 +: 8], signed
    input  logic          row_valid,
    input  logic [31:0]   a_row,            // A[m][i] = a_row[i*8 +: 8], signed
    output logic          out_valid,
    output logic [127:0]  c_row             // C[m][j] = c_row[j*32 +: 32], signed
);
    logic [7:0]   dly [0:3][0:3];           // input skew: element i passes through i registers
    logic [31:0]  a_skew;
    logic [127:0] c_raw;
    logic [31:0]  odly [0:3][0:3];          // output de-skew: column j passes through 3 - j registers
    logic [7:0]   vsr;
    always_ff @(posedge clk) begin
        for (int i = 0; i < 4; i++) begin
            dly[i][0] <= row_valid ? a_row[i*8 +: 8] : 8'd0;
            for (int k = 1; k < 4; k++) dly[i][k] <= dly[i][k-1];
        end
        for (int j = 0; j < 4; j++) begin
            odly[j][0] <= c_raw[j*32 +: 32];
            for (int k = 1; k < 4; k++) odly[j][k] <= odly[j][k-1];
        end
        vsr <= rst_n ? {vsr[6:0], row_valid} : 8'd0;
    end
    // element i uses i extra registers on top of the input register (so a_skew[i] is delayed by i + 1 in all; element 0 by one)
    always_comb begin
        a_skew[7:0]   = dly[0][0];
        a_skew[15:8]  = dly[1][1];
        a_skew[23:16] = dly[2][2];
        a_skew[31:24] = dly[3][3];
        for (int j = 0; j < 4; j++) c_row[j*32 +: 32] = (j == 3) ? c_raw[j*32 +: 32] : odly[j][2 - j];
    end
    assign out_valid = vsr[7];
    systolic4 u (.clk, .rst_n, .w_load, .w_in, .a_in(a_skew), .c_out(c_raw));
endmodule
