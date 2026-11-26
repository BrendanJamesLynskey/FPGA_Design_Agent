// PRBS-31 (x^31 + x^28 + 1): 32 new bits per word, combinational. w[31] is the first bit produced.
module prbs31_word (
    input  logic [30:0] s,
    output logic [30:0] s_n,
    output logic [31:0] w
);
    logic [30:0] t [0:32];
    assign t[0] = s;
    for (genvar i = 0; i < 32; i++) begin : g_step
        assign t[i+1] = {t[i][29:0], t[i][30] ^ t[i][27]};
        assign w[31-i] = t[i][30] ^ t[i][27];
    end
    assign s_n = t[32];
endmodule
