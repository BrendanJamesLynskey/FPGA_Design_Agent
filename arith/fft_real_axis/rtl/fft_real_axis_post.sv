// fft_real_axis_post: AXI4-Stream wrapper of the real-input FFT fft_real_post (arith brief 161, owner decision 28: favour AMBA AXI).
//
// Interfaces (AXI4-Stream, one clock `clk` = ACLK, active-low synchronous reset `aresetn`):
//   s_axis_*: input frames of N REAL samples, two per beat: tdata = {x[2m+1], x[2m]} (2 * W bits: the ODD-indexed sample in the HIGH half), N/2 beats per frame, tlast on the last (N/2-th) beat.
//             No tuser (the transform is forward only), no tkeep, tstrb, tid, tdest.
//   m_axis_*: output frames of the N/2 + 1 distinct bins X[0] .. X[N/2], one bin per beat in natural order: tdata = {imaginary, real}, WX bits each (WX = W + 1 scaled, W + LOGN + 1 unscaled; not
//             padded to bytes), tlast on the last (N/2 + 1-th) beat.
// Frame gap, enforced by the wrapper: the transform needs at least N/8 idle clocks between the last beat of a frame and the first beat of the next (measured, arith/fft_real/spec.md). The wrapper holds
// s_axis_tready LOW for N/8 clocks after every beat with tlast, so a source that streams frames back to back is held off by AXI4-Stream back-pressure and the rule can not be broken.
// What is NOT back-pressured (stated): inside a frame s_axis_tready is high, and the source must keep s_axis_tvalid high from the first to the last beat (no pause inside a frame: the core streams); the
// output cannot be stalled: m_axis_tready must be 1 whenever m_axis_tvalid is 1 (a beat that is not taken in its clock is lost; the simulation checker flags it).
// Latency: the core's, with no register added: from the clock in which the first beat of a frame is transferred to the clock in which the first output beat (bin 0) is offered.
//
// Intended primitive use (not yet measured): the core's, plus about 2 * LOGN flip-flops (the gap counter and the output beat counter) and a few LUTs.
module fft_real_axis_post #(
    parameter int LOGN      = 7,
    parameter int W         = 16,
    parameter int TW        = 16,
    parameter int SCALE     = 1,
    parameter int RND       = 1,
    parameter int CMUL      = 4,
    parameter int TWSTAGES  = 1,
    parameter int MULSTAGES = 2
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
    output logic                                                m_axis_tlast
);
    localparam int N   = 1 << LOGN;
    localparam int H   = N / 2;
    localparam int GAP = N / 8;
    localparam int WX  = (SCALE != 0) ? W + 1 : W + LOGN + 1;
    logic            rst, at_start, in_valid, in_sof, out_valid, out_sof;
    logic [WX-1:0]   out_re, out_im;
    logic [LOGN-1:0] gap, ocnt, cnt;
    always_comb begin
        rst           = ~aresetn;
        s_axis_tready = (gap == '0);
        in_valid      = s_axis_tvalid && s_axis_tready;
        in_sof        = at_start;
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            at_start <= 1'b1;
            gap      <= '0;
        end else begin
            if (in_valid) at_start <= s_axis_tlast;
            if (in_valid && s_axis_tlast) gap <= LOGN'(GAP);
            else if (gap != '0) gap <= gap - 1'b1;
        end
    end
    fft_real_post #(.LOGN(LOGN), .W(W), .TW(TW), .SCALE(SCALE), .RND(RND), .CMUL(CMUL), .TWSTAGES(TWSTAGES), .MULSTAGES(MULSTAGES)) u_core (
        .clk(clk), .rst(rst), .in_valid(in_valid), .in_sof(in_sof), .in_even(s_axis_tdata[W-1:0]), .in_odd(s_axis_tdata[2*W-1:W]),
        .out_valid(out_valid), .out_sof(out_sof), .out_re(out_re), .out_im(out_im));
    // the output beat counter: tlast on the (N/2 + 1)-th beat of an output frame
    always_comb begin
        cnt           = out_sof ? '0 : ocnt;
        m_axis_tvalid = out_valid;
        m_axis_tdata  = {out_im, out_re};
        m_axis_tlast  = out_valid && (cnt == LOGN'(H));
    end
    always_ff @(posedge clk) begin
        if (rst) ocnt <= '0;
        else if (out_valid) ocnt <= cnt + 1'b1;
    end
`ifndef SYNTHESIS
    // protocol checkers for simulation (arith/fft_common/axis_checker.sv): the source's obligations on s_axis and the design's on m_axis
    // verilator lint_off UNUSEDSIGNAL
    int chk_s_errs, chk_m_errs;
    // verilator lint_on UNUSEDSIGNAL
    axis_checker #(.DW(2 * W), .NBEAT(H), .NO_STALL(0), .CONTIG(1), .NAME("fft_real_axis_post s_axis")) u_chk_s (.clk(clk), .aresetn(aresetn), .tvalid(s_axis_tvalid), .tready(s_axis_tready), .tdata(s_axis_tdata), .tlast(s_axis_tlast), .errs(chk_s_errs));
    axis_checker #(.DW(2 * WX), .NBEAT(H + 1), .NO_STALL(1), .CONTIG(0), .NAME("fft_real_axis_post m_axis")) u_chk_m (.clk(clk), .aresetn(aresetn), .tvalid(m_axis_tvalid), .tready(m_axis_tready), .tdata(m_axis_tdata), .tlast(m_axis_tlast), .errs(chk_m_errs));
`endif
endmodule
