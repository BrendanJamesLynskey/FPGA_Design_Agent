// dotq_core: 8-way int8 dot product + bias, times mult, round-shift, clamp.
// Pipeline: go -> products -> pair sums -> acc -> acc*mult -> scaled -> y.
// done pulses with y/acc valid; y/acc then hold until the next go.
module dotq_core (
    input  logic        clk,
    input  logic        rst,        // synchronous, active high
    input  logic        go,         // one-cycle pulse, operands valid
    input  logic [63:0] act,
    input  logic [63:0] wgt,
    input  logic [31:0] bias,
    input  logic [15:0] mult,
    input  logic [4:0]  shift,
    input  logic        relu,
    output logic        done,
    output logic [7:0]  y,
    output logic [31:0] acc
);
    logic v1, v2, v3, v4, v5;

    // stage 1
    logic signed [15:0] p [8];
    logic signed [31:0] bias1;
    logic        [15:0] mult1;
    logic        [4:0]  shift1, shift2, shift3;
    logic               relu1, relu2, relu3;
    // stage 2
    logic signed [16:0] s [4];
    logic signed [31:0] bias2;
    logic        [15:0] mult2;
    // stage 3
    logic signed [31:0] acc3;
    logic        [15:0] mult3;
    // stage 4
    logic signed [48:0] prod4;
    logic        [4:0]  shift4;
    logic               relu4;
    logic signed [31:0] acc4, acc5;
    // stage 5
    logic signed [48:0] scaled5;
    logic               relu5;

    logic signed [49:0] rounded;
    logic signed [48:0] shifted;

    always_comb begin
        rounded = 50'(prod4);
        if (shift4 != 5'd0) rounded = rounded + (50'sd1 <<< (shift4 - 5'd1));
        shifted = 49'(rounded >>> shift4);
    end

    always_ff @(posedge clk) begin
        for (int i = 0; i < 8; i++) begin
            p[i] <= $signed(act[8*i +: 8]) * $signed(wgt[8*i +: 8]);
        end
        bias1  <= bias;
        mult1  <= mult;
        shift1 <= shift;
        relu1  <= relu;

        for (int i = 0; i < 4; i++) begin
            s[i] <= 17'(p[2*i]) + 17'(p[2*i+1]);
        end
        bias2  <= bias1;
        mult2  <= mult1;
        shift2 <= shift1;
        relu2  <= relu1;

        acc3   <= ((32'(s[0]) + 32'(s[1])) + (32'(s[2]) + 32'(s[3]))) + bias2;
        mult3  <= mult2;
        shift3 <= shift2;
        relu3  <= relu2;

        prod4  <= acc3 * $signed({1'b0, mult3});
        shift4 <= shift3;
        relu4  <= relu3;
        acc4   <= acc3;

        scaled5 <= shifted;
        relu5   <= relu4;
        acc5    <= acc4;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            v1 <= 1'b0; v2 <= 1'b0; v3 <= 1'b0; v4 <= 1'b0; v5 <= 1'b0;
            done <= 1'b0;
            y    <= 8'd0;
            acc  <= 32'd0;
        end else begin
            v1   <= go;
            v2   <= v1 & ~go;
            v3   <= v2 & ~go;
            v4   <= v3 & ~go;
            v5   <= v4 & ~go;
            done <= v5 & ~go;
            if (v5 && !go) begin
                acc <= acc5;
                if (scaled5 > 49'sd127)
                    y <= 8'd127;
                else if (relu5 && scaled5 < 49'sd0)
                    y <= 8'd0;
                else if (!relu5 && scaled5 < -49'sd128)
                    y <= 8'h80;
                else
                    y <= scaled5[7:0];
            end
        end
    end
endmodule
