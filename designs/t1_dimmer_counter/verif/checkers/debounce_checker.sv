// debounce_checker.sv: properties of debounce.sv from its ports only (so SymbiYosys can read it without a
// bind). It rebuilds the two-flop synchroniser and counts, from outside, how long the synchronised input has
// differed from the output level: spec.yaml behaviour.debounce.
`include "v_macros.svh"

module debounce_checker #(
    parameter int CYCLES = 1_000_000
) (
    input logic clk,
    input logic rst,
    input logic btn,
    input logic level,
    input logic press
);
    logic s1, s2, past_ok, seen_rst;
    int unsigned run;
    initial begin past_ok = 1'b0; seen_rst = 1'b0; end
    always @(posedge clk) begin
        past_ok <= 1'b1;
        if (rst) seen_rst <= 1'b1;
        if (rst) begin
            s1 <= 1'b0; s2 <= 1'b0; run <= 0;
        end else begin
            s1 <= btn; s2 <= s1;
            run <= (s2 != level && run != CYCLES - 1) ? run + 1 : 0;   // consecutive clocks s2 has differed
        end
    end

    // A_DB_PULSE: a press is a one-clock pulse
    `V_NEXT(A_DB_PULSE, press, !press)   // req: REQ-01
    // A_DB_RISE: a press is exactly a 0 -> 1 change of the debounced level
    `V_SAME(A_DB_RISE, press, level && !$past(level))   // req: REQ-02
    `V_SAME(A_DB_RISE_ONLY, level && !$past(level), press)   // req: REQ-02
    // A_DB_FALL_NO_PRESS: a release makes no press
    `V_SAME(A_DB_FALL_NO_PRESS, !level && $past(level), !press)   // req: REQ-10
    // A_DB_HOLD: the level changes only after CYCLES consecutive differing clocks (a shorter glitch is ignored)
    `V_SAME(A_DB_HOLD, level != $past(level), $past(run) == CYCLES - 1 && $past(s2) == level)   // req: REQ-02
    // A_DB_FLIP: and it does change on the clock the count reaches CYCLES
    `V_NEXT(A_DB_FLIP, s2 != level && run == CYCLES - 1, level == $past(s2))   // req: REQ-02

    `V_COVER(C_DB_PRESS, press)   // req: REQ-01
    `V_COVER(C_DB_RELEASE, !level && $past(level))   // req: REQ-10
    `V_COVER(C_DB_GLITCH_IGNORED, run == 0 && $past(run) > 0 && $past(run) < CYCLES - 1)   // req: REQ-02
endmodule
