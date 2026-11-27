// prbs31_next: 32 steps of the PRBS-31 LFSR (x^31 + x^28 + 1) in one clock.
// word[i] is the bit produced at step i; next_state is the state after 32 steps.
module prbs31_next (
    input  logic [30:0] state,
    output logic [30:0] next_state,
    output logic [31:0] word
);
    always_comb begin : steps
        logic [30:0] s;
        logic        b;
        s    = state;
        word = '0;
        for (int i = 0; i < 32; i++) begin
            b       = s[30] ^ s[27];
            s       = {s[29:0], b};
            word[i] = b;
        end
        next_state = s;
    end
endmodule
