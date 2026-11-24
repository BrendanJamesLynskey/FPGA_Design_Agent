// chk_top: YOUR instance of the block-floating-point FFT with the frame checker beside it (arith brief 161; the runner defines DUT_MODULE and DUT_PARAMS). The checker's error count is chk_errs.
`include "dut_defs.svh"
module chk_top #(
    parameter int LOGN = 6, parameter int W = 16, parameter int TW = 16, parameter int RND = 1, parameter int ORDER = 0, parameter int CMUL = 4, parameter int TWSTAGES = 1, parameter int MULSTAGES = 2
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
    output logic [$clog2(2*W+LOGN):0]   out_exp,
    output int                          chk_errs
);
    `DUT_MODULE `DUT_PARAMS u_dut (.clk, .rst, .in_valid, .in_sof, .in_inverse, .in_re, .in_im, .out_ready, .in_ready, .out_valid, .out_sof, .out_re, .out_im, .out_exp);
    frame_checker #(.NBEAT(1 << LOGN), .HAS_EXP(1), .EW($clog2(2*W+LOGN) + 1), .NAME("fft_bfp out")) u_chk (.clk, .rst, .valid(out_valid), .sof(out_sof), .ready(out_ready), .exp(out_exp), .errs(chk_errs));
endmodule
