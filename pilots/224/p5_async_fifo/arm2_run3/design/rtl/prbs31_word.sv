// PRBS-31 (x^31 + x^28 + 1), 32 new bits per word, first bit generated is the MSB of the word.
module prbs31_word (
    input  logic [30:0] state,
    output logic [30:0] next_state,
    output logic [31:0] word
);
    always_comb begin
        logic [30:0] s;
        logic        fb;
        s = state;
        word = '0;
        for (int i = 0; i < 32; i++) begin
            fb   = s[30] ^ s[27];
            s    = {s[29:0], fb};
            word = {word[30:0], fb};
        end
        next_state = s;
    end
endmodule
