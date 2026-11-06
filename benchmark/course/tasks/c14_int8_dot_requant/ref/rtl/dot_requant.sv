// Part 14 lesson 3 exercise: an int8 dot-product unit with requantisation and saturation (the core of one output of a quantised layer).
//
// N pairs of signed 8-bit numbers a[i] (activations) and w[i] (weights), packed a[i*8 +: 8], w[i*8 +: 8]. With in_valid high, one clock later (out_valid high, one clock
// of latency, rst_n clears out_valid only; synchronous, active low):
//   acc = sum(a[i] * w[i]) + bias                      (bias: signed 32 bit; the sum fits 32 bits for N up to 4096)
//   r   = (acc * mult + 2^(shift-1)) >>> shift         (mult: UNSIGNED 16 bit; shift: 1 .. 31; 64-bit signed product; >>> is the arithmetic (floor) shift)
//   y   = clamp(r, lo, 127)   with lo = 0 when relu = 1 and -128 when relu = 0
// Outputs: y (signed 8 bit) and acc (the signed 32-bit accumulator including the bias). Same ordering rule as the golden model tools/ml_models.requant.
module dot_requant #(
    parameter int N = 8
) (
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic                  in_valid,
    input  logic [N*8-1:0]        a,
    input  logic [N*8-1:0]        w,
    input  logic signed [31:0]    bias,
    input  logic [15:0]           mult,
    input  logic [4:0]            shift,
    input  logic                  relu,
    output logic                  out_valid,
    output logic signed [7:0]     y,
    output logic signed [31:0]    acc
);
    logic signed [31:0] s;
    logic signed [63:0] p, r;
    logic signed [63:0] rnd;
    always_comb begin
        s = bias;
        for (int i = 0; i < N; i++) s = s + $signed(a[i*8 +: 8]) * $signed(w[i*8 +: 8]);
        p = s * $signed({1'b0, mult});
        rnd = 64'sd1 <<< (shift - 5'd1);
        r = (p + rnd) >>> shift;
    end
    always_ff @(posedge clk) begin
        if (!rst_n) out_valid <= 1'b0;
        else out_valid <= in_valid;
        if (in_valid) begin
            acc <= s;
            if (r > 64'sd127) y <= 8'sd127;
            else if (r < (relu ? 64'sd0 : -64'sd128)) y <= relu ? 8'sd0 : -8'sd128;
            else y <= r[7:0];
        end
    end
endmodule
