// median3x3: rank-5-of-9 by rank comparison (36 parallel compares, stable ranks), one output register stage.
module median3x3 (
    input  logic        clk,
    input  logic        rst,
    input  logic        in_valid,
    input  logic [71:0] pix,        // pixel p in [8p+7:8p]
    output logic [7:0]  med,
    output logic        out_valid
);
    logic [7:0] med_c;
    logic [7:0] p [0:8];
    logic       gt [0:8][0:8];   // gt[i][j] (i<j) = p[i] > p[j]
    logic [3:0] rank [0:8];

    always_comb begin
        for (int i = 0; i < 9; i++) p[i] = pix[8*i +: 8];
        for (int i = 0; i < 9; i++)
            for (int j = 0; j < 9; j++)
                gt[i][j] = (i < j) ? (p[i] > p[j]) : 1'b0;
        for (int i = 0; i < 9; i++) begin
            rank[i] = 4'd0;
            for (int j = 0; j < 9; j++) begin
                if (j > i)      rank[i] = rank[i] + 4'(gt[i][j]);
                else if (j < i) rank[i] = rank[i] + 4'(~gt[j][i]);
            end
        end
        med_c = 8'd0;
        for (int i = 0; i < 9; i++)
            if (rank[i] == 4'd4) med_c = med_c | p[i];
    end

    always_ff @(posedge clk) begin
        med       <= med_c;
        out_valid <= in_valid & ~rst;
    end
endmodule
