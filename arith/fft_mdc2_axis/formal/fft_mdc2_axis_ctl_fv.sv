// fft_mdc2_axis_ctl_fv: the slave-side control of the AXI4-Stream 2-parallel FFT keeps its rules for every source and every sink that obey the AXI4-Stream rules (arith brief 168).
// Concurrent SVA properties over a shadow model that shares no code with the module; run by tools/run_formal.py (SymbiYosys, slang front end). The slang front end of the OSS CAD Suite used here
// does not accept the implication operators |-> and |=>, so every implication is written as the boolean `!a || b` inside the property (the same property; a previous-clock value is kept in a register).
// The environment (assumed): reset in the first clock only; a source that has offered a beat and been refused keeps offering it; a source inside a frame keeps tvalid high until the tlast beat is transferred;
// `done` (the sink took the last beat of an output frame) only for a frame that is in the block. s_last and the frame length are free (a frame may be one beat, which the module does not mind).
// Properties (asserted):
//   GAP     the first beat of a frame is transferred in the clock after the previous tlast transfer (no idle clock) or at least N/8 idle clocks after it, never 1 to N/8 - 1 idle clocks after it;
//   CREDIT  the frames in the block never exceed NB, and the module's counter equals the shadow count (frames whose first beat was transferred minus frames whose last output beat was taken);
//   INFRAME s_ready is high in every clock that is not a frame start, and at_start equals "no frame is open" (reset or the last transfer was a tlast beat);
//   FULL    a frame start is refused (s_ready low) while NB frames are in the block;
//   WIN     a frame start is accepted in the clock right after a tlast transfer whenever the block has room (so back-to-back frames are possible).
// Also covered: a back-to-back frame start, a start after the full gap, a refusal by the credit.
module fft_mdc2_axis_ctl_fv #(
    parameter int LOGN = 5,
    parameter int NB   = 2
) (
    input logic clk,
    input logic rst,
    input logic s_valid,
    input logic s_last,
    input logic done
);
    localparam int GAP = (1 << LOGN) / 8;
    logic s_ready, at_start;
    fft_mdc2_axis_ctl #(.LOGN(LOGN), .NB(NB)) u (.clk(clk), .rst(rst), .s_valid(s_valid), .s_last(s_last), .done(done), .s_ready(s_ready), .at_start(at_start));

    logic first = 1'b1;
    always_ff @(posedge clk) first <= 1'b0;
    logic        in_frame = 1'b0;                  // a frame's first beat was transferred and its tlast beat was not
    logic        seen_last = 1'b0;                 // a tlast beat was transferred since reset
    logic [7:0]  since = 8'd0;                     // clocks since the last tlast transfer (saturating); 1 in the clock right after it
    logic [3:0]  shadow = 4'd0;                    // frames in the block
    logic        xfer, start_xfer;
    always_comb begin
        xfer       = s_valid && s_ready;
        start_xfer = xfer && !in_frame;
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            in_frame  <= 1'b0;
            seen_last <= 1'b0;
            since     <= 8'd0;
            shadow    <= 4'd0;
        end else begin
            if (xfer) in_frame <= !s_last;
            if (xfer && s_last) begin
                seen_last <= 1'b1;
                since     <= 8'd1;
            end else if (since != 8'd255 && since != 8'd0) since <= since + 8'd1;
            if (start_xfer && !done) shadow <= shadow + 4'd1;
            else if (done && !start_xfer) shadow <= shadow - 4'd1;
        end
    end

    // ---- the environment
    always_comb begin
        if (first) assume (rst);
        if (!first) assume (!rst);
        if (done) assume (shadow != 4'd0);
    end
    logic refused = 1'b0;                          // the previous clock offered a beat and was refused
    always_ff @(posedge clk) refused <= s_valid && !s_ready;
    assume property (@(posedge clk) !refused || s_valid);
    assume property (@(posedge clk) !in_frame || s_valid);

    // ---- the properties
    assert property (@(posedge clk) disable iff (first || rst) !(start_xfer && seen_last) || (since == 8'd1 || since > 8'(GAP)));                      // GAP
    assert property (@(posedge clk) disable iff (first) shadow <= 4'(NB));                                                                             // CREDIT (bound)
    assert property (@(posedge clk) disable iff (first) shadow == 4'(u.infl));                                                                         // CREDIT (counter)
    assert property (@(posedge clk) disable iff (first) at_start || s_ready);                                                                      // INFRAME (ready)
    assert property (@(posedge clk) disable iff (first) at_start == !in_frame);                                                                        // INFRAME (flag)
    assert property (@(posedge clk) disable iff (first) !(at_start && shadow == 4'(NB)) || !s_ready);                                                  // FULL
    assert property (@(posedge clk) disable iff (first) !(at_start && seen_last && since == 8'd1 && shadow < 4'(NB)) || s_ready);                      // WIN
    // ---- helper invariants for the k-induction proof: where the module's window flag and gap counter must be, given the shadow's clocks since the last tlast transfer
    assert property (@(posedge clk) disable iff (first) !(!in_frame && seen_last && since == 8'd1) || (u.win && u.gap == '0));                                   // INV1
    assert property (@(posedge clk) disable iff (first) !(!in_frame && seen_last && since >= 8'd2 && since <= 8'(GAP + 1)) || (!u.win && u.gap == LOGN'(GAP + 1 - int'(since))));   // INV2
    assert property (@(posedge clk) disable iff (first) !(!in_frame && seen_last && since > 8'(GAP + 1)) || (!u.win && u.gap == '0));                              // INV3
    assert property (@(posedge clk) disable iff (first) !in_frame || (!u.win && u.gap == '0));                                                                   // INV4
    assert property (@(posedge clk) disable iff (first) seen_last || (!u.win && u.gap == '0 && since == 8'd0));                                                  // INV5
    assert property (@(posedge clk) disable iff (first) !seen_last || since != 8'd0);                                                                            // INV6
    cover property (@(posedge clk) disable iff (first) start_xfer && seen_last && since == 8'd1);
    cover property (@(posedge clk) disable iff (first) start_xfer && seen_last && since == 8'(GAP + 1));
    cover property (@(posedge clk) disable iff (first) s_valid && at_start && !s_ready && shadow == 4'(NB));
endmodule
