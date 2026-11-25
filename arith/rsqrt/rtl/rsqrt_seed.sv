// rsqrt_seed: reciprocal-square-root seed table (brief 139c). y = floor(2**F / sqrt(X_mid)) for the interval of X = x / 2**(W-2) in [1, 4) selected
// by the top A + 2 bits of x minus 2**A (3 * 2**A intervals of width 2**-A); the constant is computed at elaboration with integer arithmetic only
// (the same formula as model.seed): isqrt(2**(2F+A+1) / M), M = 2**(A+1) + 2*idx + 1.
// Primitive use (intended, not yet measured): a 3 * 2**A entry, F-bit ROM read through an (A+2)-bit subtract of 2**A (a constant, so a short
// carry chain or a LUT); distributed (LUT) ROM at A <= 6, block RAM only if the tool is told to (and then one more register of latency).
module rsqrt_seed #(
    parameter int W = 16,
    parameter int A = 7,
    parameter int F = 18
) (
    input  logic [W-1:0] x,
    output logic [F-1:0] y
);
    localparam int N = 3 << A;
    function automatic logic [N*F-1:0] mk();
        logic [N*F-1:0]  v;
        longint unsigned m, n, r, bt;
        for (int i = 0; i < N; i++) begin
            m  = (64'd1 << (A + 1)) + 64'(2 * i) + 64'd1;
            n  = (64'd1 << (2 * F + A + 1)) / m;       // the integer square root of n by the bit-pair method
            r  = 64'd0;
            bt = 64'd1 << 62;
            while (bt > n) bt = bt >> 2;
            while (bt != 64'd0) begin
                if (n >= r + bt) begin
                    n = n - (r + bt);
                    r = (r >> 1) + bt;
                end else begin
                    r = r >> 1;
                end
                bt = bt >> 2;
            end
            v[i*F +: F] = F'(r);
        end
        return v;
    endfunction
    localparam logic [N*F-1:0] TAB = mk();

    logic [A+1:0] top, idx;
    logic         unused;
    assign top = x[W-1 -: A+2];
    assign idx = top - (A+2)'(1 << A);
    assign y   = TAB[int'(idx) * F +: F];
    assign unused = &{1'b0, x[W-3-A:0]};
endmodule
