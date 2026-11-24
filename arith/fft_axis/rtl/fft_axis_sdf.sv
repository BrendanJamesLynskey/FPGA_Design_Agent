// fft_axis_sdf: AXI4-Stream wrapper of the FFT variant "sdf" (arith brief 148, owner direction: favour AMBA AXI).
//
// Interfaces (AXI4-Stream, one clock `clk` = ACLK, active-low synchronous reset `aresetn`):
//   s_axis_*: input frames. tdata = {imaginary, real}, W bits each (not padded to bytes), tlast on the last (N-th) beat of a frame, tuser[0] = 1 for an inverse transform, read on the FIRST beat of a
//             frame (the later beats' tuser is ignored). No tkeep, tstrb, tid, tdest: all beats are data.
//   m_axis_*: output frames, tdata = {imaginary, real}, WO = W (SCALE = 1) or W + LOGN bits each, tlast on the last of N beats. Natural or bit-reversed order (ORDER) as arith/fft/spec.md.
// Back-pressure: NONE (a pure streaming variant).
//   s_axis_tready is always 1 and m_axis_tready is IGNORED: it must be tied high, because the output cannot be stalled and a beat that is not taken in its clock is lost (the simulation
//   protocol checker flags a low m_axis_tready while m_axis_tvalid is high). tvalid must stay high from the first beat to the tlast beat of every frame (no pause inside a frame), and the
//   gap between frames is 0 or at least N/4 beats.
// Configuration: per-frame options (the direction) ride on tuser; there are no run-time configuration registers, so there is no AXI4-Lite interface (stated in spec.md).
// Not provided, unlike AMD's FFT IP (docs/fft_suite_plan.md section 9): a status stream, tlast_missing / tlast_unexpected events, a run-time scaling schedule, a cyclic prefix, run-time N.
// tlast on the input is used only to find the start of the next frame: a frame that does not have exactly N beats is outside the contract (not flagged, not recovered).
//
// Intended primitive use (not yet measured): the core's, plus about 3 LOGN flip-flops and a few LUTs for the beat counter and the start-of-frame flag.
module fft_axis_sdf #(
    parameter int LOGN      = 6,
    parameter int W         = 16,
    parameter int TW        = 16,
    parameter int SCALE     = 1,
    parameter int RND       = 1,
    parameter int ORDER     = 0,
    parameter int CMUL      = 4,
    parameter int TWSTAGES  = 1,
    parameter int MULSTAGES = 2
) (
    input  logic                                       clk,
    input  logic                                       aresetn,
    input  logic                                       s_axis_tvalid,
    input  logic [2*W-1:0]                             s_axis_tdata,
    input  logic                                       s_axis_tlast,
    input  logic                                       s_axis_tuser,
    output logic                                       s_axis_tready,
    input  logic                                       m_axis_tready,
    output logic                                       m_axis_tvalid,
    output logic [2*((SCALE != 0) ? W : W + LOGN)-1:0] m_axis_tdata,
    output logic                                       m_axis_tlast
);
    localparam int N  = 1 << LOGN;
    localparam int WO = (SCALE != 0) ? W : W + LOGN;
    logic            rst, at_start, core_ready, in_valid, in_sof, out_valid, out_sof;
    logic [WO-1:0]   out_re, out_im;
    logic [LOGN-1:0] ocnt, cnt;
    // verilator lint_off UNUSEDSIGNAL
    logic            unused_ready;
    // verilator lint_on UNUSEDSIGNAL
    always_comb begin
        rst           = ~aresetn;
        s_axis_tready = 1'b1;
        in_valid      = s_axis_tvalid && s_axis_tready;
        in_sof        = at_start;
        unused_ready  = core_ready;
    end
    always_ff @(posedge clk) begin
        if (rst) at_start <= 1'b1;
        else if (in_valid) at_start <= s_axis_tlast;
    end
    fft_sdf_r22 #(.LOGN(LOGN), .W(W), .TW(TW), .SCALE(SCALE), .RND(RND), .ORDER(ORDER), .CMUL(CMUL), .TWSTAGES(TWSTAGES), .MULSTAGES(MULSTAGES)) u_core (
        .clk(clk), .rst(rst), .in_valid(in_valid), .in_sof(in_sof), .in_inverse(s_axis_tuser), .in_re(s_axis_tdata[W-1:0]), .in_im(s_axis_tdata[2*W-1:W]),
        .out_ready(1'b1), .in_ready(core_ready), .out_valid(out_valid), .out_sof(out_sof), .out_re(out_re), .out_im(out_im));
    // the output beat counter: tlast on the N-th beat of an output frame (counted on transfers)
    always_comb begin
        cnt          = out_sof ? '0 : ocnt;
        m_axis_tvalid = out_valid;
        m_axis_tdata  = {out_im, out_re};
        m_axis_tlast  = out_valid && (cnt == LOGN'(N - 1));
    end
    always_ff @(posedge clk) begin
        if (rst) ocnt <= '0;
        else if (out_valid && 1'b1) ocnt <= cnt + 1'b1;
    end
`ifndef SYNTHESIS
    // protocol checkers for simulation (arith/fft_common/axis_checker.sv): the source's obligations on s_axis and the design's on m_axis
    // verilator lint_off UNUSEDSIGNAL
    int chk_s_errs, chk_m_errs;
    // verilator lint_on UNUSEDSIGNAL
    axis_checker #(.DW(2 * W), .NBEAT(N), .NO_STALL(0), .CONTIG(1), .NAME("fft_axis_sdf s_axis")) u_chk_s (.clk(clk), .aresetn(aresetn), .tvalid(s_axis_tvalid), .tready(s_axis_tready), .tdata(s_axis_tdata), .tlast(s_axis_tlast), .errs(chk_s_errs));
    axis_checker #(.DW(2 * WO), .NBEAT(N), .NO_STALL(1), .CONTIG(0), .NAME("fft_axis_sdf m_axis")) u_chk_m (.clk(clk), .aresetn(aresetn), .tvalid(m_axis_tvalid), .tready(m_axis_tready), .tdata(m_axis_tdata), .tlast(m_axis_tlast), .errs(chk_m_errs));
`endif
endmodule
