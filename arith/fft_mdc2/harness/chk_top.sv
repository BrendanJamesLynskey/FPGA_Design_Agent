// chk_top: YOUR instance of the 2-parallel FFT with the frame checker beside it (arith brief 161; the runner defines DUT_MODULE and DUT_PARAMS). The checker's error count is chk_errs.
`include "dut_defs.svh"
module chk_top #(
    parameter int LOGN = 6, parameter int W = 16, parameter int TW = 16, parameter int SCALE = 1, parameter int RND = 1, parameter int ORDER = 0, parameter int CMUL = 4, parameter int TWSTAGES = 1, parameter int MULSTAGES = 2
) (
    input  logic                                       clk,
    input  logic                                       rst,
    input  logic                                       in_valid,
    input  logic                                       in_sof,
    input  logic                                       in_inverse,
    input  logic [W-1:0]                               in_re0,
    input  logic [W-1:0]                               in_im0,
    input  logic [W-1:0]                               in_re1,
    input  logic [W-1:0]                               in_im1,
    output logic                                       in_ready,
    output logic                                       out_valid,
    output logic                                       out_sof,
    output logic [((SCALE != 0) ? W : W + LOGN)-1:0]   out_re0,
    output logic [((SCALE != 0) ? W : W + LOGN)-1:0]   out_im0,
    output logic [((SCALE != 0) ? W : W + LOGN)-1:0]   out_re1,
    output logic [((SCALE != 0) ? W : W + LOGN)-1:0]   out_im1,
    output int                                         chk_errs
);
    `DUT_MODULE `DUT_PARAMS u_dut (.clk, .rst, .in_valid, .in_sof, .in_inverse, .in_re0, .in_im0, .in_re1, .in_im1, .in_ready, .out_valid, .out_sof, .out_re0, .out_im0, .out_re1, .out_im1);
    frame_checker #(.NBEAT((1 << LOGN) / 2), .HAS_EXP(0), .EW(1), .NAME("fft_mdc2 out")) u_chk (.clk, .rst, .valid(out_valid), .sof(out_sof), .ready(1'b1), .exp(1'b0), .errs(chk_errs));
endmodule
