// prbs31_step: one 32-bit word of PRBS-31 (x^31 + x^28 + 1), 32 new bits per word.
// The first new bit is the most significant bit of the word (same as model.py).
module prbs31_step (
    input  logic [30:0] state,
    output logic [30:0] state_next,
    output logic [31:0] word
);
    always_comb begin
        logic [30:0] t;
        logic        n;
        t    = state;
        word = '0;
        for (int i = 0; i < 32; i++) begin
            n    = t[30] ^ t[27];
            t    = {t[29:0], n};
            word = {word[30:0], n};
        end
        state_next = t;
    end
endmodule
