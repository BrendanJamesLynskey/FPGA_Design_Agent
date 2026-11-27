// PRBS-31 (x^31 + x^28 + 1), 32 new bits per word, first bit generated is the MSB of the word.
/* verilator lint_off DECLFILENAME */
module p5_prbs31 (
    input  logic [30:0] s,
    output logic [31:0] word,
    output logic [30:0] s_next
);
    always_comb begin
        logic [30:0] st;
        logic        b;
        st = s;
        for (int i = 31; i >= 0; i--) begin
            b       = st[30] ^ st[27];
            st      = {st[29:0], b};
            word[i] = b;
        end
        s_next = st;
    end
endmodule
