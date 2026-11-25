// fda_conservation: the conservation invariant for a block that carries frames (brief 189 item 4; idea from Edwards 2026, ch 18).
//
//   frames in  ==  frames out  +  frames the block counted as dropped  +  frames still held inside it
//
// Bind or instantiate it in a testbench next to the block under test. It counts the frames itself, from the block's input and
// output handshakes, and compares them with the block's OWN visible drop counter and occupancy. A path that discards a frame without
// incrementing that counter (a silent drop) breaks the equality on the next clock, so the testbench fails at the frame that went
// missing instead of at a hole in a book hours later.
//
// Ports (all sampled on the rising edge of clk; the block's counters and the helper's counts update on the same edge):
//   frame_in    one-clock pulse: a frame was accepted at the block's input (valid and ready, or the block's own accept strobe)
//   frame_out   one-clock pulse: a frame left the block (valid and ready at the output)
//   drop_count  the block's own cumulative drop counter (all causes added up), read as a value, never inferred from a discard event
//   in_flight   frames held inside the block now (FIFO occupancy plus pipeline stages), as the block reports it
//   violation   sticky; set at the first edge where the equality fails
//   first_bad_in, n_in, n_out   the counts at that first failure and the live counts
// Four-state: a drop_count or in_flight with an X or Z fails the check (case inequality), so an unresolved counter cannot pass.
// Parameter SETTLE: clocks after reset release during which the check is skipped (default 0).
// The helper is not synthesisable (it uses $error); simulation only.
module fda_conservation #(
    parameter int W      = 32,
    parameter int SETTLE = 0,
    parameter bit FATAL  = 1'b0            // 1: $fatal at the first failure; 0: $error and the sticky flag
) (
    input  logic         clk,
    input  logic         rst,              // active high
    input  logic         frame_in,
    input  logic         frame_out,
    input  logic [W-1:0] drop_count,
    input  logic [W-1:0] in_flight,
    output logic         violation,
    output logic [W-1:0] n_in,
    output logic [W-1:0] n_out,
    output logic [W-1:0] first_bad_in
);
    int unsigned since_rst;
    initial begin violation = 1'b0; n_in = '0; n_out = '0; first_bad_in = '0; since_rst = 0; end
    always @(posedge clk) begin
        if (rst) begin
            n_in <= '0; n_out <= '0; since_rst <= 0;
        end else begin
            if (frame_in === 1'b1)  n_in  <= n_in + 1'b1;
            if (frame_out === 1'b1) n_out <= n_out + 1'b1;
            since_rst <= since_rst + 1;
            if (since_rst >= SETTLE && !violation &&
                (^{drop_count, in_flight} === 1'bx || n_in !== n_out + drop_count + in_flight)) begin
                violation    <= 1'b1;
                first_bad_in <= n_in;
                if (FATAL) $fatal(1, "fda_conservation: in=%0d out=%0d dropped=%0d in_flight=%0d", n_in, n_out, drop_count, in_flight);
                else       $error("fda_conservation: in=%0d out=%0d dropped=%0d in_flight=%0d", n_in, n_out, drop_count, in_flight);
            end
        end
    end
endmodule
