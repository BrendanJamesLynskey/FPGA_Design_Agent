// median_core: 9 unsigned 8-bit pixels -> 5th smallest, one output register.
// Rank counting: all 36 pairwise compares in parallel, a stable rank per pixel
// (ties broken by index), and the pixel of rank 4 is selected. Shallow, no
// feedback, no DSP, no multiplier. Valid delayed exactly one clock.
module median_core (
    input  logic        clk,
    input  logic        rst,        // synchronous, active high
    input  logic        in_valid,
    input  logic [71:0] in_win,     // pixel p in [8p+7:8p]
    output logic        out_valid,
    output logic [7:0]  out_med
);
    logic [7:0] px [9];
    for (genvar i = 0; i < 9; i++) begin : g_px
        assign px[i] = in_win[8*i +: 8];
    end

    // gt[i][j] (i<j): px[i] > px[j]
    logic gt [9][9];
    for (genvar i = 0; i < 9; i++) begin : g_gi
        for (genvar j = 0; j < 9; j++) begin : g_gj
            if (i < j) begin : g_c
                assign gt[i][j] = px[i] > px[j];
            end else begin : g_n
                assign gt[i][j] = 1'b0;
            end
        end
    end

    // bef[i][j]: pixel j sorts before pixel i
    logic bef [9][9];
    for (genvar i = 0; i < 9; i++) begin : g_bi
        for (genvar j = 0; j < 9; j++) begin : g_bj
            if (j < i) begin : g_lo
                assign bef[i][j] = !gt[j][i];
            end else if (j > i) begin : g_hi
                assign bef[i][j] = gt[i][j];
            end else begin : g_self
                assign bef[i][j] = 1'b0;
            end
        end
    end

    logic [8:0] sel;
    for (genvar i = 0; i < 9; i++) begin : g_rank
        logic [3:0] rank;
        always_comb begin
            rank = 4'd0;
            for (int j = 0; j < 9; j++) rank = rank + {3'd0, bef[i][j]};
        end
        assign sel[i] = (rank == 4'd4);
    end

    logic [7:0] med_c;
    always_comb begin
        med_c = 8'd0;
        for (int i = 0; i < 9; i++) med_c = med_c | (px[i] & {8{sel[i]}});
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            out_valid <= 1'b0;
            out_med   <= 8'd0;
        end else begin
            out_valid <= in_valid;
            out_med   <= med_c;
        end
    end
endmodule
