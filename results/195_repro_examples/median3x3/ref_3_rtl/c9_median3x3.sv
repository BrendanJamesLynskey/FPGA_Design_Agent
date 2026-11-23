// 3x3 median of nine 8-bit pixels: rank-compare network, one output register (latency 1).
// Pixel i is the median when exactly 4 other pixels rank below it (ties broken by index).
module c9_median3x3 (
    input  logic        clk,
    input  logic        rst,
    input  logic        valid_in,
    input  logic [71:0] pix,        // pixel p in [8p+7:8p]
    output logic        valid_out,
    output logic [7:0]  median
);
    logic [7:0] p [9];
    logic       lt [9][9];          // lt[i][j]: pixel j ranks below pixel i
    logic [8:0] sel;
    logic [7:0] med_c;
    logic [3:0] cnt [9];

    always_comb begin
        for (int i = 0; i < 9; i++) p[i] = pix[8*i +: 8];
        for (int i = 0; i < 9; i++)
            for (int j = 0; j < 9; j++)
                lt[i][j] = (j < i) ? (p[j] <= p[i]) : (j > i) ? (p[j] < p[i]) : 1'b0;
        for (int i = 0; i < 9; i++) begin
            cnt[i] = 4'd0;
            for (int j = 0; j < 9; j++) cnt[i] = cnt[i] + {3'b000, lt[i][j]};
            sel[i] = (cnt[i] == 4'd4);
        end
        med_c = 8'h00;
        for (int i = 0; i < 9; i++) med_c = med_c | (p[i] & {8{sel[i]}});
    end

    always_ff @(posedge clk) begin
        if (rst) valid_out <= 1'b0;
        else     valid_out <= valid_in;
        median <= med_c;
    end
endmodule
