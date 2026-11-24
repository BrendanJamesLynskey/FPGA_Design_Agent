// fp_mul_dsp: floating-point multiplier, significand product on DSP blocks (arith brief 139e, variant "dsp").
//
// Function (arith/fp_mul/spec.md): y = a * b for IEEE-754-style binary formats of EXP exponent and MAN fraction bits, round to nearest even, canonical quiet NaN, no exception
// flags (infinity times zero is NaN). SUBNORM = 1: full subnormal support; SUBNORM = 0: flush to zero (subnormal inputs read as zero, results below the smallest normal number
// become zero). STAGES register ranks (0 to 3, latency STAGES, one product per clock): rank 3 after the output, rank 2 before the significand multiplier (the DSP's operand
// registers, AREG and BREG), rank 1 as well after it (the DSP's product register, PREG). No reset: the pipeline holds data only.
//
// Structure: unpack, multiply the two SP-bit significands (SP = MAN + 1) into an exact 2 * SP bit product, add the exponents, normalise (a leading-zero count when SUBNORM = 1,
// because a subnormal operand leaves leading zeros; one bit when SUBNORM = 0), round and pack (fp_pack). The product is exact; only the rounding step loses information.
//
// Intended primitive use (stated before any Vivado run; not yet measured): the SP x SP unsigned product `*` is mapped to DSP48E1 (7 series, 25 x 18 signed multiplier, so an unsigned
// operand has 24 usable bits and one DSP covers 24 x 17) or DSP48E2 (UltraScale+, 27 x 18): binary32 (SP = 24) is about 4 DSP48E1 (2 x 2 tiles, 24 x 24 needs tiling on the 18-bit
// side) or 2 DSP48E2, bfloat16 (SP = 8) and binary16 (SP = 11) one DSP. The use_dsp attribute asks for the DSP explicitly. The rest is LUTs and a carry chain: the leading-zero
// normaliser (2 * SP bits, SUBNORM = 1 only), the exponent adder and the rounding incrementer. With STAGES 3 the operand and product registers can be absorbed by the DSP.
module fp_mul_dsp #(
    parameter int EXP     = 8,
    parameter int MAN     = 23,
    parameter int SUBNORM = 1,
    parameter int STAGES  = 3
) (
    // verilator lint_off UNUSEDSIGNAL
    input  logic                clk,
    // verilator lint_on UNUSEDSIGNAL
    input  logic [EXP+MAN:0]    a,
    input  logic [EXP+MAN:0]    b,
    output logic [EXP+MAN:0]    y
);
    localparam int W   = EXP + MAN + 1;
    localparam int SP  = MAN + 1;
    localparam int PW  = 2 * SP;
    localparam int LW  = $clog2(PW) + 1;
    localparam int EW  = (EXP + 1 > $clog2(PW + 4) + 1 ? EXP + 1 : $clog2(PW + 4) + 1) + 2;
    localparam logic [EXP-1:0] ONES = '1;
    localparam logic [W-1:0]   QNAN = {1'b0, ONES, 1'b1, {(MAN - 1){1'b0}}};
    localparam int BIAS = (1 << (EXP - 1)) - 1;

    // ---- phase 1: unpack, special cases, exponent sum -----------------------------------------------------------------------
    logic sa, sb;
    logic [EXP-1:0] ea, eb;
    logic [MAN-1:0] fa, fb;
    assign {sa, ea, fa} = a;
    assign {sb, eb, fb} = b;
    logic a_nan, b_nan, a_inf, b_inf, a_zero, b_zero;
    assign a_nan  = (ea == ONES) && (fa != '0);
    assign b_nan  = (eb == ONES) && (fb != '0);
    assign a_inf  = (ea == ONES) && (fa == '0);
    assign b_inf  = (eb == ONES) && (fb == '0);
    assign a_zero = (ea == '0) && (SUBNORM == 0 || fa == '0);          // a subnormal is a zero when flushing
    assign b_zero = (eb == '0) && (SUBNORM == 0 || fb == '0);

    logic [SP-1:0] siga0, sigb0;
    assign siga0 = {(ea != '0), fa};
    assign sigb0 = {(eb != '0), fb};
    logic signed [EW-1:0] t0;                                           // biased exponent of a result whose product has its leading one at bit 2 * MAN
    assign t0 = $signed(EW'(ea == '0 ? EXP'(1) : ea)) + $signed(EW'(eb == '0 ? EXP'(1) : eb)) - $signed(EW'(BIAS));
    logic sg0;
    assign sg0 = sa ^ sb;

    logic         sp_v0;
    logic [W-1:0] sp_x0;
    always_comb begin
        sp_v0 = 1'b1;
        if (a_nan || b_nan)                              sp_x0 = QNAN;
        else if ((a_inf && b_zero) || (b_inf && a_zero)) sp_x0 = QNAN;
        else if (a_inf || b_inf)                         sp_x0 = {sg0, ONES, {MAN{1'b0}}};
        else if (a_zero || b_zero)                       sp_x0 = {sg0, {(W - 1){1'b0}}};
        else begin
            sp_v0 = 1'b0;
            sp_x0 = '0;
        end
    end

    // ---- rank 1: the multiplier's operand registers -------------------------------------------------------------------------
    logic                 sp_v1, sg1;
    logic [W-1:0]         sp_x1;
    logic [SP-1:0]        siga1, sigb1;
    logic signed [EW-1:0] t1;
    if (STAGES >= 2) begin : g_r1
        always_ff @(posedge clk) begin
            sp_v1 <= sp_v0;
            sp_x1 <= sp_x0;
            sg1   <= sg0;
            siga1 <= siga0;
            sigb1 <= sigb0;
            t1    <= t0;
        end
    end else begin : g_n1
        assign sp_v1 = sp_v0;
        assign sp_x1 = sp_x0;
        assign sg1   = sg0;
        assign siga1 = siga0;
        assign sigb1 = sigb0;
        assign t1    = t0;
    end

    // ---- phase 2: the significand product -----------------------------------------------------------------------------------
    (* use_dsp = "yes" *) logic [PW-1:0] pp2;
    assign pp2 = siga1 * sigb1;

    // ---- rank 2: the multiplier's product register --------------------------------------------------------------------------
    logic                 sp_v2, sg2;
    logic [W-1:0]         sp_x2;
    logic [PW-1:0]        pp3;
    logic signed [EW-1:0] t2;
    if (STAGES >= 3) begin : g_r2
        always_ff @(posedge clk) begin
            sp_v2 <= sp_v1;
            sp_x2 <= sp_x1;
            sg2   <= sg1;
            pp3   <= pp2;
            t2    <= t1;
        end
    end else begin : g_n2
        assign sp_v2 = sp_v1;
        assign sp_x2 = sp_x1;
        assign sg2   = sg1;
        assign pp3   = pp2;
        assign t2    = t1;
    end

    // ---- phase 3: normalise, round, pack ------------------------------------------------------------------------------------
    logic [PW-1:0] nrm;
    logic [LW-1:0] lz;
    if (SUBNORM != 0) begin : g_full
        fp_norm #(.NW(PW), .LW(LW)) u_norm (.v(pp3), .n(nrm), .lz(lz));
    end else begin : g_one
        // flush to zero: both significands are normal, so the product has its leading one in the top bit or the one below
        assign lz  = pp3[PW-1] ? LW'(0) : LW'(1);
        assign nrm = pp3[PW-1] ? pp3 : {pp3[PW-2:0], 1'b0};
    end
    logic signed [EW-1:0] er;
    assign er = t2 + 1 - $signed(EW'(lz));
    logic [W-1:0] packed_y;
    fp_pack #(.EXP(EXP), .MAN(MAN), .SUBNORM(SUBNORM), .NW(PW), .EW(EW)) u_pack (.sgn(sg2), .er(er), .n(nrm), .stk(1'b0), .y(packed_y));
    logic [W-1:0] y_c;
    assign y_c = sp_v2 ? sp_x2 : packed_y;

    // ---- rank 3: the output register ----------------------------------------------------------------------------------------
    if (STAGES >= 1) begin : g_r3
        always_ff @(posedge clk) y <= y_c;
    end else begin : g_n3
        assign y = y_c;
    end
endmodule
