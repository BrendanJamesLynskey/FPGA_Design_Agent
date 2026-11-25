// fft_mdc2_axis_ctl: the slave-side control of fft_mdc2_axis_par2 (arith brief 168): the frame-start flag, the inter-frame gap rule and the bank credit (the AXI4-Stream tready of the input).
//
// It holds no data. Inputs are the transfer-relevant signals of the slave stream (s_valid, s_last), and `done`, one pulse when the last beat of an output frame has been transferred on the master stream.
// Rules it enforces on s_ready, which depends on registers only (never on s_valid):
//   gap     after the beat with tlast is transferred, the next frame may start in the very next clock (no idle clock) or after at least GAP = N/8 idle clocks, never after 1 to GAP - 1: the streaming
//           rule of the 2-parallel core (arith/fft_mdc2/spec.md). The gap counter is 0 after a tlast transfer, so s_ready is high in the one clock after it (the window); if no beat is transferred in that clock, `win` (set
//           by the tlast transfer, cleared by the next clock) loads the counter with GAP - 1 and s_ready falls for GAP - 1 clocks and rises again, which makes the first beat of the next frame at least GAP idle clocks
//           after the last beat of the previous one.
//   credit  at most NB frames are in the block at once (accepted, output not yet completely taken): s_ready is low at a frame start while NB are in flight. A frame needs one bank of the output frame store from its first
//           output word until its last output beat is transferred, so the credit makes a store overflow impossible whatever the sink does.
//   inside a frame s_ready is high (the core streams); the source must keep s_valid high from the first to the last beat.
// at_start is high from reset and after every tlast transfer until the first beat of the next frame is transferred: it is the core's in_sof for the beat on offer.
//
// Intended primitive use (not yet measured): about 2 * LOGN + 6 flip-flops and under 20 LUT.
module fft_mdc2_axis_ctl #(
    parameter int LOGN = 6,
    parameter int NB   = 3
) (
    input  logic clk,
    input  logic rst,
    input  logic s_valid,
    input  logic s_last,
    input  logic done,
    output logic s_ready,
    output logic at_start
);
    localparam int GAP = (1 << LOGN) / 8;
    localparam int CW  = $clog2(NB + 1);
    logic            win, xfer, up;
    logic [LOGN-1:0] gap;
    logic [CW-1:0]   infl;
    always_comb begin
        s_ready = at_start ? ((gap == '0) && (infl != CW'(NB))) : 1'b1;
        xfer    = s_valid && s_ready;
        up      = xfer && at_start;
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            at_start <= 1'b1;
            win      <= 1'b0;
            gap      <= '0;
            infl     <= '0;
        end else begin
            if (xfer) begin
                at_start <= s_last;
                win      <= s_last;
                gap      <= '0;
            end else if (win) begin
                win <= 1'b0;
                gap <= LOGN'(GAP - 1);
            end else if (gap != '0) begin
                gap <= gap - 1'b1;
            end
            if (up && !done) infl <= infl + 1'b1;
            else if (done && !up) infl <= infl - 1'b1;
        end
    end
endmodule
