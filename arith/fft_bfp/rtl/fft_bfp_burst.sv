// fft_bfp_burst: block-floating-point FFT on the memory-based burst core (arith brief 161, variant "burst").
//
// The unscaled fft_burst_r2 (SCALE = 0, bit-reversed output, words of W + LOGN bits) feeds fft_bfp_out, which finds the frame's exponent while the frame is stored, then reads it out in natural
// order (ORDER = 0) or bit-reversed order (ORDER = 1) with every part shifted to W bits. out_exp is the frame's exponent s: the true unscaled transform of the frame is
// (out_re + j out_im) * 2**s (forward: sum x[n] exp(-j 2 pi n k / N); inverse: exp(+j ...), no 1/N), to within the error stated in spec.md.
// Handshakes are the burst core's: in_sof only while in_ready is 1; out_ready stalls the output (out_valid, out_sof and the data are held), and the core in turn waits when both
// frame banks are full, so nothing is lost.
// Latency (in_sof to out_sof, no stall): N + LOGN * (N / 2 + MULSTAGES + 3) + 1 + N + 2: the core's latency, then one frame to store and 2 clocks to read.
//
// Intended primitive use (stated before any Vivado run; not yet measured): the core's, plus 2 x N x 2 * (W + LOGN) bits of frame store (block RAM) and the shifter and exponent logic of fft_bfp_out.
module fft_bfp_burst #(
    parameter int LOGN      = 6,
    parameter int W         = 16,
    parameter int TW        = 16,
    parameter int RND       = 1,
    parameter int ORDER     = 0,
    parameter int CMUL      = 4,
    parameter int TWSTAGES  = 1,
    parameter int MULSTAGES = 2
) (
    input  logic                        clk,
    input  logic                        rst,
    input  logic                        in_valid,
    input  logic                        in_sof,
    input  logic                        in_inverse,
    input  logic [W-1:0]                in_re,
    input  logic [W-1:0]                in_im,
    input  logic                        out_ready,
    output logic                        in_ready,
    output logic                        out_valid,
    output logic                        out_sof,
    output logic [W-1:0]                out_re,
    output logic [W-1:0]                out_im,
    output logic [$clog2(2*W+LOGN):0]   out_exp
);
    localparam int WC = W + LOGN;
    logic          c_valid, c_sof, wr_ready;
    logic [WC-1:0] c_re, c_im;
    fft_burst_r2 #(.LOGN(LOGN), .W(W), .TW(TW), .SCALE(0), .RND(RND), .ORDER(1), .CMUL(CMUL), .TWSTAGES(TWSTAGES), .MULSTAGES(MULSTAGES)) u_core (
        .clk(clk), .rst(rst), .in_valid(in_valid), .in_sof(in_sof), .in_inverse(in_inverse), .in_re(in_re), .in_im(in_im), .out_ready(wr_ready),
        .in_ready(in_ready), .out_valid(c_valid), .out_sof(c_sof), .out_re(c_re), .out_im(c_im));
    fft_bfp_out #(.LOGN(LOGN), .W(W), .RND(RND), .ORDER(ORDER)) u_out (
        .clk(clk), .rst(rst), .in_valid(c_valid), .in_sof(c_sof), .in_re(c_re), .in_im(c_im), .out_ready(out_ready), .wr_ready(wr_ready),
        .out_valid(out_valid), .out_sof(out_sof), .out_re(out_re), .out_im(out_im), .out_exp(out_exp));
endmodule
