// fft_bitrev: reverse the order of the bits of an address (arith brief 148). Combinational. It is an involution and a permutation of 0 .. 2**LOGN - 1;
// both are proved for LOGN 1 to 8 by SymbiYosys (arith/fft_reorder/formal).
//
// Intended primitive use (not yet measured): wires only.
module fft_bitrev #(
    parameter int LOGN = 6
) (
    input  logic [LOGN-1:0] a,
    output logic [LOGN-1:0] y
);
    always_comb begin
        for (int i = 0; i < LOGN; i++) y[i] = a[LOGN-1-i];
    end
endmodule
