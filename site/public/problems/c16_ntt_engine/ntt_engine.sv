// source: solutions/p16l07_ntt/ntt_engine.sv (course file, unchanged below this line)
// Part 16 lesson 7 exercise: an NTT engine for ML-KEM (FIPS 203): 256 coefficients modulo q = 3329, one butterfly per clock, in place. Given: ntt_zetas_pkg.sv (function zeta(k): the table of FIPS 203 appendix A).
//   ld_en with ld_addr / ld_data writes coefficient ld_addr (any time the engine is idle). rd_addr / rd_data is an asynchronous read of coefficient rd_addr (rd_data follows rd_addr within the same clock).
//   start (one clock, only while !busy) with inverse = 0 runs the forward transform (algorithm 9), with inverse = 1 the inverse (algorithm 10, including the final multiplication of every coefficient by 128^-1 = 3303).
//   Forward: 7 layers (len = 128, 64, ..., 2) of 128 butterflies, one per clock = 896 clocks. For layer l (l = 0..6) with len = 128 >> l and G = 1 << l groups of 2*len coefficients: group g = c / len, offset j = c % len
//   (c = the butterfly counter 0..127 of the layer), the pair is (g*2*len + j, g*2*len + j + len) and the twiddle is zeta(G + g)  [k runs 1, 2, 3, ... through the layers].
//   Inverse: 7 layers (len = 2, 4, ..., 128) of 128 butterflies with G = 128 / len groups and twiddle zeta(2*G - 1 - g) [k runs 127, 126, ... down to 1], then 256 clocks multiplying coefficient i by 3303: 896 + 256 = 1152 clocks.
//   Butterfly, forward: t = zeta * f[hi] mod q; f[hi] = f[lo] - t; f[lo] = f[lo] + t.  Inverse: t = f[lo]; f[lo] = t + f[hi]; f[hi] = zeta * (f[hi] - t).  All mod q, with Barrett reduction (no % operator).
//   busy is high from the clock after start for exactly 896 (forward) or 1152 (inverse) clocks; done is high for exactly one clock after the last. rst_n is synchronous, active low, clears busy and done only.
module ntt_engine (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        ld_en,
    input  logic [7:0]  ld_addr,
    input  logic [11:0] ld_data,
    input  logic        start,
    input  logic        inverse,
    output logic        busy,
    output logic        done,
    input  logic [7:0]  rd_addr,
    output logic [11:0] rd_data
);
    import ntt_zetas_pkg::*;
    localparam int Q = 3329;
    logic [11:0] mem [0:255];
    logic        inv_r, scaling;
    logic [2:0]  layer;                    // 0..6
    logic [6:0]  c;                        // butterfly counter in the layer
    logic [7:0]  sc;                       // scaling counter
    assign rd_data = mem[rd_addr];

    function automatic logic [11:0] barrett(input logic [23:0] p);
        logic [36:0] m;
        logic [11:0] t;
        logic [23:0] r;
        m = p * 13'd5039;
        t = m[35:24];
        r = p - t * 12'd3329;
        barrett = (r >= Q) ? 12'(r - Q) : r[11:0];
    endfunction
    function automatic logic [11:0] addq(input logic [11:0] u, input logic [11:0] v);
        logic [12:0] s;
        s = u + v;
        addq = (s >= Q) ? 12'(s - Q) : s[11:0];
    endfunction
    function automatic logic [11:0] subq(input logic [11:0] u, input logic [11:0] v);
        subq = (u >= v) ? (u - v) : 12'(u + Q - v);
    endfunction

    // address generation for the current butterfly
    logic [7:0]  len, lo, hi;
    logic [7:0]  g, j;
    logic [7:0]  gcount;
    logic [6:0]  kidx;
    logic [11:0] z, vlo, vhi, tt, nlo, nhi;
    always_comb begin
        len = inv_r ? (8'd2 << layer) : (8'd128 >> layer);
        gcount = 8'd128 / len;
        g = {1'b0, c} / len;
        j = {1'b0, c} % len;
        lo = g * 2 * len + j;
        hi = lo + len;
        kidx = inv_r ? 7'(2 * gcount - 1 - g) : 7'(gcount + g);
        z = zeta(kidx);
        vlo = mem[lo];
        vhi = mem[hi];
        tt = barrett(z * vhi);
        if (!inv_r) begin nlo = addq(vlo, tt); nhi = subq(vlo, tt); end
        else begin nlo = addq(vlo, vhi); nhi = barrett(z * subq(vhi, vlo)); end
    end
    always_ff @(posedge clk) begin
        done <= 1'b0;
        if (ld_en && !busy) mem[ld_addr] <= ld_data;
        if (!rst_n) busy <= 1'b0;
        else if (!busy) begin
            if (start) begin busy <= 1'b1; inv_r <= inverse; layer <= 3'd0; c <= 7'd0; scaling <= 1'b0; sc <= 8'd0; end
        end else if (!scaling) begin
            mem[lo] <= nlo;
            mem[hi] <= nhi;
            if (c == 7'd127) begin
                c <= 7'd0;
                if (layer == 3'd6) begin
                    if (inv_r) scaling <= 1'b1;
                    else begin busy <= 1'b0; done <= 1'b1; end
                end else layer <= layer + 1'b1;
            end else c <= c + 1'b1;
        end else begin
            mem[sc] <= barrett(mem[sc] * 12'd3303);
            sc <= sc + 1'b1;
            if (sc == 8'd255) begin busy <= 1'b0; done <= 1'b1; end
        end
    end
endmodule
