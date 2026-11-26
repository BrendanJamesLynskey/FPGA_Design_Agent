// fft_bitrev_fv: the bit-reversal address map is a permutation and an involution, for every address (arith brief 148). Combinational: the proof is exhaustive.
// The independent facts: a single set bit moves from position k to position LOGN-1-k (checked for every k by a generate loop, not by the module's own loop), the map is its own
// inverse, and two different addresses never map to the same one (so it is a bijection of 0 .. 2**LOGN - 1). Run by tools/run_formal.py (SymbiYosys, slang front end).
module fft_bitrev_fv #(
    parameter int LOGN = 6
) (
    input logic        clk,
    input logic [LOGN-1:0] a,
    input logic [LOGN-1:0] b
);
    logic [LOGN-1:0] ya, yb, yya;
    fft_bitrev #(.LOGN(LOGN)) u_a  (.a(a),  .y(ya));
    fft_bitrev #(.LOGN(LOGN)) u_b  (.a(b),  .y(yb));
    fft_bitrev #(.LOGN(LOGN)) u_aa (.a(ya), .y(yya));
    always_comb begin
        INVOLUTION: assert (yya == a);
        INJECTIVE:  assert (a == b || ya != yb);
    end
    for (genvar k = 0; k < LOGN; k++) begin : g_onehot
        always_comb begin
            ONEHOT: assert (a != (LOGN'(1) << k) || ya == (LOGN'(1) << (LOGN - 1 - k)));
        end
    end
endmodule
