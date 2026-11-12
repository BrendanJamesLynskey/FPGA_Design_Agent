// Part 14 lesson 3 exercise: an int8 dot-product unit with requantisation and saturation (the core of one output of a quantised layer).
//
// N pairs of signed 8-bit numbers a[i] (activations) and w[i] (weights), packed a[i*8 +: 8], w[i*8 +: 8]. With in_valid high, the result is produced
// after three clocks: two clocks to register the dot-product accumulator in pipelined stages, followed by one clock for requantisation and output registration.
//   acc = sum(a[i] * w[i]) + bias
//   r   = (acc * mult + 2^(shift-1)) >>> shift
//   y   = clamp(r, lo, 127)   with lo = 0 when relu = 1 and -128 when relu = 0
// Outputs: y (signed 8 bit) and acc (the signed 32-bit accumulator including the bias).
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
    logic signed [31:0] s_lo, s_hi;
    logic signed [31:0] s_lo_q, s_hi_q;
    logic signed [31:0] s_q;
    logic [15:0]        mult_p, mult_q;
    logic [4:0]         shift_p, shift_q, shift_r;
    logic               relu_p, relu_q, relu_r;
    logic               valid_p, valid_q, valid_r;
    logic signed [31:0] acc_r;

    logic signed [63:0] p_q, r;
    logic signed [63:0] rnd;

    always_comb begin
        s_lo = bias;
        s_hi = 32'sd0;
        for (int i = 0; i < N; i++) begin
            if (i < (N / 2))
                s_lo = s_lo + $signed(a[i*8 +: 8]) * $signed(w[i*8 +: 8]);
            else
                s_hi = s_hi + $signed(a[i*8 +: 8]) * $signed(w[i*8 +: 8]);
        end

        rnd = 64'sd1 <<< (shift_r - 5'd1);
        r = (p_q + rnd) >>> shift_r;
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            valid_p   <= 1'b0;
            valid_q   <= 1'b0;
            valid_r   <= 1'b0;
            out_valid <= 1'b0;
        end else begin
            s_lo_q    <= s_lo;
            s_hi_q    <= s_hi;
            mult_p    <= mult;
            shift_p   <= shift;
            relu_p    <= relu;
            valid_p   <= in_valid;

            s_q       <= s_lo_q + s_hi_q;
            mult_q    <= mult_p;
            shift_q   <= shift_p;
            relu_q    <= relu_p;
            valid_q   <= valid_p;

            p_q       <= s_q * $signed({1'b0, mult_q});
            acc_r     <= s_q;
            shift_r   <= shift_q;
            relu_r    <= relu_q;
            valid_r   <= valid_q;
            out_valid <= valid_r;

            if (valid_r) begin
                acc <= acc_r;
                if (r > 64'sd127) y <= 8'sd127;
                else if (r < (relu_r ? 64'sd0 : -64'sd128))
                    y <= relu_r ? 8'sd0 : -8'sd128;
                else y <= r[7:0];
            end
        end
    end
endmodule
