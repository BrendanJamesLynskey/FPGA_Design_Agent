// fft_mdc2_axis_par2: AXI4-Stream wrapper of the 2-parallel FFT fft_mdc2_par2 with block floating point (arith brief 168, owner decision 28: favour AMBA AXI).
//
// Interfaces (AXI4-Stream, one clock `clk` = ACLK, active-low synchronous reset `aresetn`):
//   s_axis_*: input frames of N complex samples, TWO per beat: tdata = {im1, re1, im0, re0}, W bits each (not padded to bytes), two's complement; sample 0 = x[2m] (the EVEN-indexed one) is in the LOW half and sample 1 =
//             x[2m + 1] in the HIGH half; N/2 beats per frame, tlast on the last (N/2-th) beat. tuser[0] = 1 for an inverse transform, read on the FIRST beat of a frame (later beats' tuser is ignored).
//             No tkeep, tstrb, tid, tdest.
//   m_axis_*: output frames of N complex samples, two per beat, as a block-floating-point frame: tdata = {im1, re1, im0, re0}, W bits each, sample 0 = X[k] and sample 1 = X[k + N/2] at beat k (natural order, k = 0 .. N/2 - 1),
//             tlast on the last (N/2-th) beat. tuser = the frame's block exponent s (signed, EW = $clog2(2 * W + LOGN) + 1 bits), valid on the FIRST beat of the frame, and held at the same value on every other beat of
//             that frame; the true value of every part of the frame is part * 2**s (forward: sum x[n] exp(-j 2 pi n k / N); inverse: exp(+j ...), no 1/N). Why the first beat: the exponent is known only when the whole frame
//             has been seen, which is before the first output beat is released, so the first beat can carry it and a downstream scaler can latch it before any data arrives.
// Back-pressure:
//   s_axis_tready is a register decode, never from tvalid. Inside a frame it is HIGH; the source must keep tvalid high from the first to the last beat of a frame (the core streams). At a frame start it is
//   low (a) for N/8 - 1 clocks after the one clock that follows a tlast beat, when no beat was transferred in that clock, so that the idle clocks between two frames are 0 or at least N/8 (the streaming rule of the
//   2-parallel core, measured: arith/fft_mdc2), and (b) while NB frames are in the block (output not yet completely taken): the block holds NB output banks (default 4: the smallest number that sustains one frame per N/2 clocks).
//   m_axis_tready may be low at any time and for any length: the output is held (tvalid, tdata, tuser, tlast stable until taken); input frames then wait at the credit above, nothing is lost.
// Latency: from the clock in which the first beat of a frame is transferred on s_axis to the clock in which the first beat of the output frame is offered on m_axis with m_axis_tready not stalling: the core's
//   (bit-reversed pair order) latency plus N/2 + 2.
//
// Intended primitive use (not yet measured): the core fft_mdc2_par2 at SCALE = 0, plus the output stage fft_bfp_out_pair (NB banks x N/2 words x 4 * (W + LOGN) bits of block RAM, four shifters and an exponent
// encoder) and about 2 * LOGN + 6 flip-flops of control.
module fft_mdc2_axis_par2 #(
    parameter int LOGN      = 6,
    parameter int W         = 16,
    parameter int TW        = 16,
    parameter int RND       = 1,
    parameter int CMUL      = 4,
    parameter int TWSTAGES  = 1,
    parameter int MULSTAGES = 2,
    parameter int NB        = 4
) (
    input  logic                        clk,
    input  logic                        aresetn,
    input  logic                        s_axis_tvalid,
    input  logic [4*W-1:0]              s_axis_tdata,
    input  logic [0:0]                  s_axis_tuser,
    input  logic                        s_axis_tlast,
    output logic                        s_axis_tready,
    input  logic                        m_axis_tready,
    output logic                        m_axis_tvalid,
    output logic [4*W-1:0]              m_axis_tdata,
    output logic [$clog2(2*W+LOGN):0]   m_axis_tuser,
    output logic                        m_axis_tlast
);
    localparam int N  = 1 << LOGN;
    localparam int H  = N / 2;
    localparam int WC = W + LOGN;
    localparam int EW = $clog2(2 * W + LOGN) + 1;
    logic          rst, at_start, in_valid, done;
    logic          c_valid, c_sof;
    logic [WC-1:0] c_re0, c_im0, c_re1, c_im1;
    logic [W-1:0]  o_re0, o_im0, o_re1, o_im1;
    logic          o_valid, o_last;
    logic [EW-1:0] o_exp;
    // verilator lint_off UNUSEDSIGNAL
    logic          in_ready_u;
    // verilator lint_on UNUSEDSIGNAL
    always_comb begin
        rst      = ~aresetn;
        in_valid = s_axis_tvalid && s_axis_tready;
        done     = o_valid && m_axis_tready && o_last;
    end
    fft_mdc2_axis_ctl #(.LOGN(LOGN), .NB(NB)) u_ctl (
        .clk(clk), .rst(rst), .s_valid(s_axis_tvalid), .s_last(s_axis_tlast), .done(done), .s_ready(s_axis_tready), .at_start(at_start));
    fft_mdc2_par2 #(.LOGN(LOGN), .W(W), .TW(TW), .SCALE(0), .RND(RND), .ORDER(1), .CMUL(CMUL), .TWSTAGES(TWSTAGES), .MULSTAGES(MULSTAGES)) u_core (
        .clk(clk), .rst(rst), .in_valid(in_valid), .in_sof(at_start), .in_inverse(s_axis_tuser[0]),
        .in_re0(s_axis_tdata[W-1:0]), .in_im0(s_axis_tdata[2*W-1:W]), .in_re1(s_axis_tdata[3*W-1:2*W]), .in_im1(s_axis_tdata[4*W-1:3*W]),
        .in_ready(in_ready_u), .out_valid(c_valid), .out_sof(c_sof), .out_re0(c_re0), .out_im0(c_im0), .out_re1(c_re1), .out_im1(c_im1));
    fft_bfp_out_pair #(.LOGN(LOGN), .W(W), .RND(RND), .NB(NB)) u_out (
        .clk(clk), .rst(rst), .in_valid(c_valid), .in_sof(c_sof), .in_re0(c_re0), .in_im0(c_im0), .in_re1(c_re1), .in_im1(c_im1), .out_ready(m_axis_tready),
        .out_valid(o_valid), .out_last(o_last), .out_re0(o_re0), .out_im0(o_im0), .out_re1(o_re1), .out_im1(o_im1), .out_exp(o_exp));
    always_comb begin
        m_axis_tvalid = o_valid;
        m_axis_tdata  = {o_im1, o_re1, o_im0, o_re0};
        m_axis_tuser  = o_exp;
        m_axis_tlast  = o_last;
    end
`ifndef SYNTHESIS
    // protocol checkers for simulation (arith/fft_common/axis_checker.sv): the source's obligations on s_axis and the design's on m_axis (the sink may stall, so NO_STALL = 0: rules H1, H2 and F1 apply;
    // tuser is checked with tdata for stability)
    // verilator lint_off UNUSEDSIGNAL
    int chk_s_errs, chk_m_errs;
    // verilator lint_on UNUSEDSIGNAL
    axis_checker #(.DW(4 * W + 1), .NBEAT(H), .NO_STALL(0), .CONTIG(1), .NAME("fft_mdc2_axis_par2 s_axis")) u_chk_s (
        .clk(clk), .aresetn(aresetn), .tvalid(s_axis_tvalid), .tready(s_axis_tready), .tdata({s_axis_tuser, s_axis_tdata}), .tlast(s_axis_tlast), .errs(chk_s_errs));
    axis_checker #(.DW(4 * W + EW), .NBEAT(H), .NO_STALL(0), .CONTIG(0), .NAME("fft_mdc2_axis_par2 m_axis")) u_chk_m (
        .clk(clk), .aresetn(aresetn), .tvalid(m_axis_tvalid), .tready(m_axis_tready), .tdata({m_axis_tuser, m_axis_tdata}), .tlast(m_axis_tlast), .errs(chk_m_errs));
`endif
endmodule
