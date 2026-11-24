// fpx_ref: the specification of the floating-point add, multiply and multiply-add as plain wide integer arithmetic (arith brief 139e). Not a design to build: a reference for
// SymbiYosys (the proofs of arith/fp_*/formal) and the packaged harness (arith/fp_*/harness/assertions.sv). It shares no code with the RTL variants.
//
// OP = 0: y = a + b; OP = 1: y = a * b; OP = 2: y = a * b + c (one rounding); c is unused unless OP = 2. EXP, MAN, SUBNORM as in spec.md.
// Method: every finite operand is an integer times 2**Lbase (Lbase = 1 - bias - MAN, the subnormal step); a product is an integer times 2**(2 * Lbase). All terms are put in
// units of 2**(2 * Lbase), where they are integers (a window of 2 * SP + 2 * (2**EXP - 1) + 8 bits holds the largest), added as signed integers, and the magnitude is
// rounded to nearest even at the kept-bit position max(msb - MAN, subnormal step) (SUBNORM = 1) or msb - MAN (flush to zero, the exponent range unbounded), then packed.
module fpx_ref #(
    parameter int EXP     = 3,
    parameter int MAN     = 2,
    parameter int SUBNORM = 1,
    parameter int OP      = 2
) (
    input  logic [EXP+MAN:0] a,
    input  logic [EXP+MAN:0] b,
    input  logic [EXP+MAN:0] c,
    output logic [EXP+MAN:0] y
);
    localparam int W     = EXP + MAN + 1;
    localparam int SP    = MAN + 1;
    localparam int EMAXF = (1 << EXP) - 1;
    localparam int BIAS  = (1 << (EXP - 1)) - 1;
    localparam int SH    = BIAS + MAN - 1;                           // -Lbase: a term of an operand is shifted left by this to reach units of 2**(2 * Lbase)
    localparam int WD    = 2 * SP + 2 * EMAXF + 8;
    localparam logic [W-1:0] QNAN = {1'b0, EMAXF[EXP-1:0], 1'b1, {(MAN - 1){1'b0}}};

    function automatic logic is_nan(input logic [W-1:0] x);
        return (x[W-2:MAN] == EMAXF[EXP-1:0]) && (x[MAN-1:0] != '0);
    endfunction
    function automatic logic is_inf(input logic [W-1:0] x);
        return (x[W-2:MAN] == EMAXF[EXP-1:0]) && (x[MAN-1:0] == '0);
    endfunction
    function automatic logic is_zero(input logic [W-1:0] x);
        return (x[W-2:MAN] == '0) && (SUBNORM == 0 || x[MAN-1:0] == '0);
    endfunction
    function automatic logic [SP-1:0] sig_of(input logic [W-1:0] x);
        return is_zero(x) ? '0 : {(x[W-2:MAN] != '0), x[MAN-1:0]};
    endfunction
    function automatic int eff_exp(input logic [W-1:0] x);
        return (x[W-2:MAN] == '0) ? 1 : int'(x[W-2:MAN]);
    endfunction

    logic [WD-1:0]        m1, m2, mag, hi, hi2, rem, half;
    logic signed [WD:0]   t1, t2, q;
    logic                 s1, s2, z1, z2, neg;
    int                   p, kpos, e;

    always_comb begin
        y = '0;
        m1 = '0; m2 = '0; mag = '0; hi = '0; hi2 = '0; rem = '0; half = '0;
        t1 = '0; t2 = '0; q = '0; s1 = 1'b0; s2 = 1'b0; z1 = 1'b0; z2 = 1'b0; neg = 1'b0; p = 0; kpos = 0; e = 0;
        // ---- special operands --------------------------------------------------------------------------------------------------
        if (OP == 0) begin
            s1 = a[W-1]; s2 = b[W-1];
            if (is_nan(a) || is_nan(b))                                    y = QNAN;
            else if (is_inf(a) && is_inf(b) && s1 != s2)                   y = QNAN;
            else if (is_inf(a))                                            y = {s1, EMAXF[EXP-1:0], {MAN{1'b0}}};
            else if (is_inf(b))                                            y = {s2, EMAXF[EXP-1:0], {MAN{1'b0}}};
        end else begin
            s1 = a[W-1] ^ b[W-1];
            s2 = (OP == 2) ? c[W-1] : s1;
            if (is_nan(a) || is_nan(b) || (OP == 2 && is_nan(c)))          y = QNAN;
            else if ((is_inf(a) && is_zero(b)) || (is_inf(b) && is_zero(a))) y = QNAN;
            else if (is_inf(a) || is_inf(b))                               y = (OP == 2 && is_inf(c) && c[W-1] != s1) ? QNAN : {s1, EMAXF[EXP-1:0], {MAN{1'b0}}};
            else if (OP == 2 && is_inf(c))                                 y = {s2, EMAXF[EXP-1:0], {MAN{1'b0}}};
        end
        // ---- finite operands: exact integer sum ---------------------------------------------------------------------------------
        if (y == '0 && !(is_nan(a) || is_inf(a) || is_nan(b) || is_inf(b) || (OP == 2 && (is_nan(c) || is_inf(c))))) begin
            if (OP == 0) begin
                m1 = WD'(sig_of(a)) << (eff_exp(a) - 1 + SH);
                m2 = WD'(sig_of(b)) << (eff_exp(b) - 1 + SH);
                z1 = is_zero(a); z2 = is_zero(b);
            end else begin
                m1 = (WD'(sig_of(a)) * WD'(sig_of(b))) << (eff_exp(a) - 1 + eff_exp(b) - 1);
                z1 = is_zero(a) || is_zero(b);
                if (OP == 2) begin
                    m2 = WD'(sig_of(c)) << (eff_exp(c) - 1 + SH);
                    z2 = is_zero(c);
                end else begin
                    z2 = 1'b1;
                end
            end
            t1 = s1 ? -$signed({1'b0, m1}) : $signed({1'b0, m1});
            t2 = s2 ? -$signed({1'b0, m2}) : $signed({1'b0, m2});
            q  = t1 + t2;
            neg = q[WD];
            mag = neg ? WD'(-q) : WD'(q);
            if (mag == '0) begin
                y = {(z1 && z2 && s1 && s2), {(W - 1){1'b0}}};
            end else begin
                for (int i = 0; i < WD; i++) if (mag[i]) p = i;
                kpos = p - MAN;
                if (SUBNORM != 0 && kpos < SH) kpos = SH;
                if (kpos > 0) begin
                    hi   = mag >> kpos;
                    rem  = mag & ((WD'(1) << kpos) - WD'(1));
                    half = WD'(1) << (kpos - 1);
                    hi2  = hi + ((rem > half || (rem == half && hi[0])) ? WD'(1) : WD'(0));
                end else begin
                    hi2 = mag << (-kpos);
                end
                if (hi2 == (WD'(1) << (MAN + 1))) begin
                    hi2 = hi2 >> 1;
                    kpos = kpos + 1;
                end
                e = kpos + 2 - BIAS - MAN;                                  // the biased exponent of hi2's leading bit when hi2 >= 2**MAN
                if (hi2 < (WD'(1) << MAN))             y = {neg, {EXP{1'b0}}, hi2[MAN-1:0]};            // subnormal (only with SUBNORM = 1)
                else if (e >= EMAXF)                   y = {neg, EMAXF[EXP-1:0], {MAN{1'b0}}};
                else if (e <= 0)                       y = {neg, {(W - 1){1'b0}}};                       // flush to zero
                else                                   y = {neg, e[EXP-1:0], hi2[MAN-1:0]};
            end
        end
    end
endmodule
