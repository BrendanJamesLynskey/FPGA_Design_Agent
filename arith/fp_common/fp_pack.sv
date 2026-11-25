// fp_pack: the rounding and packing stage every floating-point variant of the arithmetic library shares (arith brief 139e).
// round-to-nearest-even and pack. It takes a NORMALISED significand n (msb set, NW bits) whose leading bit has the biased exponent `er` (a signed number:
// the value is n / 2**(NW-1) * 2**(er - bias)), an extra sticky bit `stk` for anything already lost below n, and the sign. It
//   * denormalises (right shift with sticky) when SUBNORM = 1 and er < 1, so the result is a subnormal number with the exponent field 0;
//   * rounds to nearest, ties to even, on the guard bit and the OR of everything below it;
//   * adds the rounding increment to the packed {exponent, fraction} pattern, so a carry out of the fraction increments the exponent, a subnormal that rounds
//     up becomes the smallest normal number, and the largest finite number that rounds up becomes the infinity pattern, with no special case;
//   * returns infinity when the rounded exponent reaches the all-ones field, and (SUBNORM = 0, flush to zero) a zero when the rounded exponent is below 1.
// The caller handles zero, NaN and infinity operands and exact-zero sums; fp_pack is only for a nonzero finite magnitude.
//
// Intended primitive use (stated before any Vivado run; not yet measured): LUTs and carry chains only: one NW-wide barrel shifter in each of fp_norm and the
// subnormal right shift, one EW + MAN bit incrementer. No DSP, no block RAM, no flip-flops (pure combinational).
module fp_pack #(
    parameter int EXP     = 8,
    parameter int MAN     = 23,
    parameter int SUBNORM = 1,
    parameter int NW      = 2 * (MAN + 1),
    parameter int EW      = EXP + 2
) (
    input  logic                  sgn,
    input  logic signed [EW-1:0]  er,
    input  logic [NW-1:0]         n,
    input  logic                  stk,
    output logic [EXP+MAN:0]      y
);
    // verilator lint_off UNUSEDSIGNAL
    logic [2*NW-1:0]        t;
    // verilator lint_on UNUSEDSIGNAL
    logic [NW-1:0]          nn;
    logic                   st;
    logic signed [EW-1:0]   ef;
    int                     kc;
    always_comb begin
        t  = '0;
        kc = 0;
        if (SUBNORM != 0 && er < 1) begin
            kc = 1 - int'(er);
            if (kc > NW) kc = NW;
            t  = {n, {NW{1'b0}}} >> kc;
            nn = t[2*NW-1:NW];
            st = stk | (|t[NW-1:0]);
            ef = '0;
        end else begin
            nn = n;
            st = stk;
            ef = er;
        end
    end
    logic [MAN-1:0] frac;
    logic           guard, rest, inc;
    assign frac  = nn[NW-2 -: MAN];
    assign guard = nn[NW-2-MAN];
    assign rest  = (|nn[NW-3-MAN:0]) | st;
    assign inc   = guard & (rest | frac[0]);

    logic signed [EW+MAN-1:0] wsum;
    assign wsum = {ef, frac} + (EW + MAN)'(inc);
    logic signed [EW-1:0] expo;
    assign expo = wsum[EW+MAN-1:MAN];
    always_comb begin
        if (int'(expo) >= (1 << EXP) - 1)                y = {sgn, {EXP{1'b1}}, {MAN{1'b0}}};
        else if (SUBNORM == 0 && int'(expo) <= 0)        y = {sgn, {(EXP + MAN){1'b0}}};
        else                                             y = {sgn, expo[EXP-1:0], wsum[MAN-1:0]};
    end
endmodule
