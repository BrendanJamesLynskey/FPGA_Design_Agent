// PRBS-31 (x^31 + x^28 + 1): 32 new bits per word, bit i is the i-th generated bit.
module prbs31_step (
    input  logic [30:0] s,
    output logic [31:0] w,
    output logic [30:0] s_n
);
    logic [30:0] t;
    logic        nb;
    always_comb begin
        t  = s;
        w  = '0;
        nb = 1'b0;
        for (int i = 0; i < 32; i++) begin
            nb   = t[30] ^ t[27];
            t    = {t[29:0], nb};
            w[i] = nb;
        end
        s_n = t;
    end
endmodule
