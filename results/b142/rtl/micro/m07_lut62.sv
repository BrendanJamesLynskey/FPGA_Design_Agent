// m07_lut62: sixteen pairs of 5-input functions sharing the same five inputs (each pair fits one LUT6_2).
module m07_lut62 (input logic clk, input logic [4:0] x [16], output logic [31:0] y);
    logic [4:0] xq [16];
    always_ff @(posedge clk) begin
        for (int i = 0; i < 16; i++) begin
            xq[i] <= x[i];
            y[2*i]   <= (xq[i][0] & xq[i][1]) ^ (xq[i][2] | xq[i][3]) ^ xq[i][4];
            y[2*i+1] <= (xq[i][0] ^ xq[i][2]) & ((xq[i][1] | xq[i][4]) ^ xq[i][3]);
        end
    end
endmodule
