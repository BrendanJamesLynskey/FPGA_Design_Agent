// fft_twiddle_fv: the quarter-turn symmetry of the twiddle table holds exactly for every index (arith brief 148).
// exp(-j (a + pi/2)) = -j exp(-j a), so for the index m of an angle and the index m + N/4 (mod N) of the angle a quarter turn on, wr(m + N/4) = wi(m) and wi(m + N/4) = -wr(m), EXACTLY
// (the table is built from one quarter wave and the same two rounded values serve both). Two instances read m and m + N/4 in the same clock; the check applies once ST clocks have
// passed since the start. This proves the quadrant folding, the signs and the mirrored read; it does not prove the table's values (the model's tests and exhaustive simulation do).
module fft_twiddle_fv #(
    parameter int LOGC = 6,
    parameter int TW   = 16,
    parameter int ST   = 1
) (
    input logic              clk,
    input logic [LOGC-1:0]   m
);
    logic [LOGC-1:0] m2;
    logic [TW-1:0]   wr1, wi1, wr2, wi2;
    fft_twiddle_quarter #(.LOGC(LOGC), .TW(TW), .STAGES(ST)) u1 (.clk(clk), .m(m),  .wr(wr1), .wi(wi1));
    fft_twiddle_quarter #(.LOGC(LOGC), .TW(TW), .STAGES(ST)) u2 (.clk(clk), .m(m2), .wr(wr2), .wi(wi2));
    logic [2:0] warm = 3'd0;
    always_comb m2 = m + LOGC'(1 << (LOGC - 2));
    always_ff @(posedge clk) if (warm != 3'd7) warm <= warm + 3'd1;
    always_comb begin
        SYM_COS: assert (warm < 3'(ST) + 3'd1 || wr2 == wi1);
        SYM_SIN: assert (warm < 3'(ST) + 3'd1 || wi2 == -wr1);
    end
endmodule
