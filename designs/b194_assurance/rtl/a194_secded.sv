// a194_secded.sv: single-error-correcting, double-error-detecting code, Hamming(71,64) plus an overall parity bit = 72 bits.
// Bit 0 of the 72-bit word is the overall parity, bits 1..71 are the Hamming codeword (check bits at the power-of-two positions
// 1, 2, 4, 8, 16, 32, 64; data bits at the others). Used for the fabric ECC variant of the FIFO (brief 194).
package a194_secded_pkg;
    function automatic logic [71:0] encode(input logic [63:0] d);
        logic [71:0] cw;
        int k;
        cw = '0;
        k = 0;
        for (int i = 1; i <= 71; i++) begin
            if ((i & (i - 1)) != 0) begin   // not a power of two: a data position
                cw[i] = d[k];
                k++;
            end
        end
        for (int p = 0; p < 7; p++) begin
            logic par;
            par = 1'b0;
            for (int i = 1; i <= 71; i++) if ((i >> p) & 1) par ^= cw[i];
            cw[1 << p] = par;
        end
        cw[0] = ^cw[71:1];
        return cw;
    endfunction

    // returns {dbit, sbit, corrected data}
    function automatic logic [65:0] decode(input logic [71:0] cw_in);
        logic [71:0] cw;
        logic [6:0]  syn;
        logic        ovr, sbit, dbit;
        logic [63:0] d;
        int k;
        cw  = cw_in;
        syn = '0;
        for (int i = 1; i <= 71; i++) if (cw[i]) syn ^= 7'(i);
        ovr  = ^cw;
        sbit = ovr;                      // odd overall parity: one error (or any odd number)
        dbit = !ovr && (syn != 0);       // even parity with a non-zero syndrome: two errors
        if (ovr && syn <= 7'd71) cw[syn] = ~cw[syn];   // syn 0 flips the overall-parity bit itself
        k = 0;
        d = '0;
        for (int i = 1; i <= 71; i++) begin
            if ((i & (i - 1)) != 0) begin
                d[k] = cw[i];
                k++;
            end
        end
        return {dbit, sbit, d};
    endfunction
endpackage
