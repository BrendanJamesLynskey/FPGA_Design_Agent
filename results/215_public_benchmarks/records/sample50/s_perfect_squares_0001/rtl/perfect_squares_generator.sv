// Perfect squares generator with sticky 32-bit saturation (no multiplier).
// Reset forces the output to 1 immediately (combinational override), while the
// state registers use a synchronous reset.
module perfect_squares_generator (
    input  logic        clk,
    input  logic        reset,
    output logic [31:0] sqr_o
);
    logic [15:0] n;
    logic [31:0] sqr;
    logic        sat;
    logic [32:0] sum;

    assign sum   = {1'b0, sqr} + {16'b0, n, 1'b0} + 33'd1;
    assign sqr_o = reset ? 32'd1 : sqr;

    always_ff @(posedge clk) begin
        if (reset) begin
            n   <= 16'd1;
            sqr <= 32'd1;
            sat <= 1'b0;
        end else begin
            n <= n + 16'd1;
            if (sat || sum[32]) begin
                sqr <= 32'hFFFFFFFF;
                sat <= 1'b1;
            end else begin
                sqr <= sum[31:0];
            end
        end
    end
endmodule
