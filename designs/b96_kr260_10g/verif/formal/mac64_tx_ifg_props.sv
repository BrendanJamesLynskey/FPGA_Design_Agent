// mac64_tx_ifg_props.sv (brief 158): the two interframe-gap conditions of mac64_tx.sv that brief 146's code coverage showed no simulation can reach, written as formal properties; attached by bind
// (mac64_tx_ifg_bind.sv), the RTL is not edited. The port names are mac64_tx's own signal names (the bind connects them by name with .*).
//
//   RTL line 76, the frame end spills into a second word:  ifg <= (n + 4 - 8 > 4) ? 2'd2 : 2'd1;   the true arm needs n > 8
//   RTL line 79, the frame end fits in the first word:     ifg <= (n + 4 > 4)     ? 2'd2 : 2'd1;   the false arm needs n <= 0
// n = s_nb1 + 1 with s_nb1 three bits, so n is 1 to 8: line 76's true arm and line 79's false arm cannot be taken. The same conditions, with the state and the handshake that lead to the
// assignment, are written as `cover` statements (task unreach_cover must report them unreached) and as assertions (task unreach_prove must prove them); the reachable arms are covered as the
// control (task reach_cover must reach them all), so a wrong state encoding or an unreachable `S_DATA` could not make the unreachable ones look unreachable for the wrong reason.
// State encoding of mac64_tx's state_t: S_IDLE 0, S_DATA 1, S_TAIL 2, S_IFG 3.
module mac64_tx_ifg_props (
    input logic        clk, rst, adv,
    input logic        s_valid, s_last,
    input logic [2:0]  s_nb1,
    input logic [1:0]  st,
    input int          n
);
    // A1: the design starts in reset (the proof is from reset, like the simulations).
    logic init = 1'b1;
    always_ff @(posedge clk) init <= 1'b0;
    always_comb if (init) assume (rst);

    // the situation in which the RTL executes the two assignments
    logic at_last, spill, fits;
    assign at_last = !rst && adv && st == 2'd1 && s_valid && s_last;
    assign spill   = at_last && (n + 4 >= 8);
    assign fits    = at_last && !(n + 4 >= 8);

`ifdef FV_UNREACH
    // the two unreachable arms
    UNREACH_A: cover property (@(posedge clk) spill && (n + 4 - 8 > 4));
    UNREACH_B: cover property (@(posedge clk) fits && !(n + 4 > 4));
`endif
`ifdef FV_PROVE
    always_comb P_RANGE: assert (n >= 1 && n <= 8);
    always_comb P_ARM_A: assert (!(spill && (n + 4 - 8 > 4)));
    always_comb P_ARM_B: assert (!(fits && !(n + 4 > 4)));
`endif
`ifdef FV_REACH
    // control: the other arm of each condition, and the state S_DATA with a last word, are reachable; for every n from 1 to 8 the right arm is taken
    R_SPILL_1:  cover property (@(posedge clk) spill && !(n + 4 - 8 > 4));
    R_FITS_2:   cover property (@(posedge clk) fits && (n + 4 > 4));
    R_N1:       cover property (@(posedge clk) at_last && n == 1);
    R_N4:       cover property (@(posedge clk) at_last && n == 4);
    R_N5:       cover property (@(posedge clk) at_last && n == 5);
    R_N8:       cover property (@(posedge clk) at_last && n == 8);
    // brief 202 (143c rigour): the antecedent of each assertion of the proof task, so that a proof is not vacuous: the situation in which each could be broken
    P_RANGE__ante: cover property (@(posedge clk) at_last);
    P_ARM_A__ante: cover property (@(posedge clk) spill);
    P_ARM_B__ante: cover property (@(posedge clk) fits);
`endif
endmodule
