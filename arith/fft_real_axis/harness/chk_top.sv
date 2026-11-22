// chk_top: YOUR instance of the AXI4-Stream real-input FFT with the AXI4-Stream protocol checkers beside it (arith brief 161; the runner defines DUT_MODULE and DUT_PARAMS). The error counts are
// chk_s_errs (the source's obligations on s_axis: valid held with stable data until accepted, tvalid kept high through a frame) and chk_m_errs (the design's on m_axis, no stall).
`include "dut_defs.svh"
module chk_top #(
    parameter int LOGN = 7, parameter int W = 16, parameter int TW = 16, parameter int SCALE = 1, parameter int RND = 1, parameter int CMUL = 4, parameter int TWSTAGES = 1, parameter int MULSTAGES = 2
) (
    input  logic                                                clk,
    input  logic                                                aresetn,
    input  logic                                                s_axis_tvalid,
    input  logic [2*W-1:0]                                      s_axis_tdata,
    input  logic                                                s_axis_tlast,
    output logic                                                s_axis_tready,
    input  logic                                                m_axis_tready,
    output logic                                                m_axis_tvalid,
    output logic [2*((SCALE != 0) ? W + 1 : W + LOGN + 1)-1:0]  m_axis_tdata,
    output logic                                                m_axis_tlast,
    output int                                                  chk_s_errs,
    output int                                                  chk_m_errs
);
    localparam int WX = (SCALE != 0) ? W + 1 : W + LOGN + 1;
    `DUT_MODULE `DUT_PARAMS u_dut (.clk, .aresetn, .s_axis_tvalid, .s_axis_tdata, .s_axis_tlast, .s_axis_tready, .m_axis_tready, .m_axis_tvalid, .m_axis_tdata, .m_axis_tlast);
    axis_checker #(.DW(2 * W), .NBEAT((1 << LOGN) / 2), .NO_STALL(0), .CONTIG(1), .NAME("fft_real_axis s_axis")) u_chk_s (.clk, .aresetn, .tvalid(s_axis_tvalid), .tready(s_axis_tready), .tdata(s_axis_tdata), .tlast(s_axis_tlast), .errs(chk_s_errs));
    axis_checker #(.DW(2 * WX), .NBEAT((1 << LOGN) / 2 + 1), .NO_STALL(1), .CONTIG(0), .NAME("fft_real_axis m_axis")) u_chk_m (.clk, .aresetn, .tvalid(m_axis_tvalid), .tready(m_axis_tready), .tdata(m_axis_tdata), .tlast(m_axis_tlast), .errs(chk_m_errs));
endmodule
