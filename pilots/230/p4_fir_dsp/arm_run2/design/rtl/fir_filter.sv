// 32-tap symmetric FIR, Q1.15, 1 sample per clock.
// Pipeline: history(1) -> pre-add(2) -> multiply(3) -> adder tree 4 levels(4..7) -> round(8) -> shift/saturate(9).
// Coefficients are the 16 unique values of data/coeffs.hex (tap 0 first, h[k] = h[31-k]).
module fir_filter (
    input  logic               clk,
    input  logic               clr,        // synchronous: zero history and flush the pipeline
    input  logic               in_valid,
    input  logic signed [15:0] in_x,
    output logic               out_valid,
    output logic [15:0]        out_y,
    output logic               out_sat
);
    localparam int ACCW = 38;
    logic signed [15:0] H [16];
    assign H[0]  = 16'h001f; assign H[1]  = 16'hffdb; assign H[2]  = 16'hffab; assign H[3]  = 16'h0000;
    assign H[4]  = 16'h00bd; assign H[5]  = 16'h00aa; assign H[6]  = 16'hff0f; assign H[7]  = 16'hfde6;
    assign H[8]  = 16'h0000; assign H[9]  = 16'h03d5; assign H[10] = 16'h032c; assign H[11] = 16'hfbb6;
    assign H[12] = 16'hf659; assign H[13] = 16'h0000; assign H[14] = 16'h18cc; assign H[15] = 16'h2edb;

    // stage 1: history d[k] = x[n-k] (shifts only when a sample is accepted)
    logic signed [15:0] d [32];
    logic [8:0] v;   // valid pipeline, v[0] = history stage
    always_ff @(posedge clk) begin
        if (clr) begin
            for (int i = 0; i < 32; i++) d[i] <= '0;
        end else if (in_valid) begin
            d[0] <= in_x;
            for (int i = 1; i < 32; i++) d[i] <= d[i-1];
        end
    end
    always_ff @(posedge clk) begin
        if (clr) v <= '0;
        else     v <= {v[7:0], in_valid};
    end

    // stage 2: pre-add
    logic signed [16:0] p [16];
    always_ff @(posedge clk)
        for (int k = 0; k < 16; k++) p[k] <= 17'(d[k]) + 17'(d[31-k]);

    // stage 3: multiply on DSP
    (* use_dsp = "yes" *) logic signed [32:0] m [16];
    always_ff @(posedge clk)
        for (int k = 0; k < 16; k++) m[k] <= p[k] * H[k];

    // stages 4..7: adder tree
    logic signed [ACCW-1:0] t1 [8];
    logic signed [ACCW-1:0] t2 [4];
    logic signed [ACCW-1:0] t3 [2];
    logic signed [ACCW-1:0] t4;
    always_ff @(posedge clk) begin
        for (int i = 0; i < 8; i++) t1[i] <= ACCW'(m[2*i]) + ACCW'(m[2*i+1]);
        for (int i = 0; i < 4; i++) t2[i] <= t1[2*i] + t1[2*i+1];
        for (int i = 0; i < 2; i++) t3[i] <= t2[2*i] + t2[2*i+1];
        t4 <= t3[0] + t3[1];
    end

    // stage 8: rounding constant; stage 9: arithmetic shift and saturation
    logic signed [ACCW-1:0] acc;
    always_ff @(posedge clk) acc <= t4 + ACCW'(16384);

    logic signed [ACCW-1:0] sh;
    assign sh = acc >>> 15;
    always_ff @(posedge clk) begin
        if (sh > ACCW'(32767))        begin out_y <= 16'h7fff; out_sat <= 1'b1; end
        else if (sh < -ACCW'(32768))  begin out_y <= 16'h8000; out_sat <= 1'b1; end
        else                          begin out_y <= sh[15:0]; out_sat <= 1'b0; end
    end
    assign out_valid = v[8];
endmodule
