// fp_fma_fused: fused multiply-add, y = a * b + c with ONE rounding (arith brief 139e, variant "fused").
//
// Function (arith/fp_fma/spec.md): the exact value a * b + c, rounded once to nearest even, for IEEE-754-style binary formats of EXP exponent and MAN fraction bits. Special cases as
// IEEE 754 fusedMultiplyAdd with the library's conventions (canonical quiet NaN, infinity times zero is NaN even when c is a NaN, no exception flags). SUBNORM = 1: full subnormal
// support; SUBNORM = 0: flush to zero. STAGES register ranks (0 to 4, latency STAGES, one result per clock): rank 4 after the output, rank 3 between the adder and the normaliser,
// rank 2 between the multiplier and the aligner (the DSP's product register), rank 1 between the unpacking and the multiplier (the DSP's operand registers). No reset.
//
// Structure: unpack; with SUBNORM = 1 normalise each significand (leading-zero count and shift, so the product's leading one is at one of two positions); multiply the SP-bit
// significands of a and b exactly (2 * SP bits, SP = MAN + 1); place the product and the SP-bit significand of c in a window of 3 * SP + 3 bits, the one with the larger exponent
// fixed with its leading bit at the top and the other shifted right by the exponent difference (a sticky bit keeps what falls off the bottom); add or subtract as signed numbers and
// take the magnitude; leading-zero count and left shift (fp_norm); round to nearest even and pack (fp_pack). Nothing is rounded before the end.
//
// Intended primitive use (stated before any Vivado run; not yet measured): the SP x SP unsigned product `*` on DSP blocks: binary32 (SP = 24) about 4 DSP48E1 or 2 DSP48E2, bfloat16
// and binary16 one. In LUTs: one (3 * SP + 3)-bit barrel shifter (the aligner), a (3 * SP + 4)-bit adder/subtractor and negation on carry chains, one (3 * SP + 3)-bit
// leading-zero normaliser (the widest block), the rounding incrementer; with SUBNORM = 1 three SP-bit input normalisers (a, b, c) and a denormalising right shifter, which
// SUBNORM = 0 omits. A binary32 instance is on the order of 1200 to 1800 LUT6 and 4 DSP48E1 on 7 series. Flip-flops only for the rank registers (STAGES).
module fp_fma_fused #(
    parameter int EXP     = 8,
    parameter int MAN     = 23,
    parameter int SUBNORM = 1,
    parameter int STAGES  = 4
) (
    // verilator lint_off UNUSEDSIGNAL
    input  logic                clk,
    // verilator lint_on UNUSEDSIGNAL
    input  logic [EXP+MAN:0]    a,
    input  logic [EXP+MAN:0]    b,
    input  logic [EXP+MAN:0]    c,
    output logic [EXP+MAN:0]    y
);
    localparam int W    = EXP + MAN + 1;
    localparam int SP   = MAN + 1;
    localparam int PW   = 2 * SP;
    localparam int WW   = 3 * SP + 3;                  // the alignment window
    localparam int LWS  = $clog2(SP) + 1;
    localparam int LW   = $clog2(WW) + 1;
    localparam int EW   = (EXP + 3 > $clog2(8 * SP + 8) + 1 ? EXP + 3 : $clog2(8 * SP + 8) + 1) + 1;
    localparam int BIAS = (1 << (EXP - 1)) - 1;
    localparam logic [EXP-1:0] ONES = '1;
    localparam logic [W-1:0]   QNAN = {1'b0, ONES, 1'b1, {(MAN - 1){1'b0}}};

    // ---- phase 1: unpack, special cases, normalise the inputs -----------------------------------------------------------------
    logic sa, sb, sc;
    logic [EXP-1:0] ea, eb, ec;
    logic [MAN-1:0] fa, fb, fc;
    assign {sa, ea, fa} = a;
    assign {sb, eb, fb} = b;
    assign {sc, ec, fc} = c;
    logic a_nan, b_nan, c_nan, a_inf, b_inf, c_inf, a_zero, b_zero, c_zero;
    assign a_nan  = (ea == ONES) && (fa != '0);
    assign b_nan  = (eb == ONES) && (fb != '0);
    assign c_nan  = (ec == ONES) && (fc != '0);
    assign a_inf  = (ea == ONES) && (fa == '0);
    assign b_inf  = (eb == ONES) && (fb == '0);
    assign c_inf  = (ec == ONES) && (fc == '0);
    assign a_zero = (ea == '0) && (SUBNORM == 0 || fa == '0);
    assign b_zero = (eb == '0) && (SUBNORM == 0 || fb == '0);
    assign c_zero = (ec == '0) && (SUBNORM == 0 || fc == '0);
    logic sp0;                                         // sign of the product
    assign sp0 = sa ^ sb;

    logic [SP-1:0] ra, rb, rc, siga0, sigb0, sigc0;    // significands before and after normalisation
    assign ra = a_zero ? '0 : {(ea != '0), fa};
    assign rb = b_zero ? '0 : {(eb != '0), fb};
    assign rc = c_zero ? '0 : {(ec != '0), fc};
    logic [LWS-1:0] lza, lzb, lzc;
    if (SUBNORM != 0) begin : g_in
        fp_norm #(.NW(SP), .LW(LWS)) u_na (.v(ra), .n(siga0), .lz(lza));
        fp_norm #(.NW(SP), .LW(LWS)) u_nb (.v(rb), .n(sigb0), .lz(lzb));
        fp_norm #(.NW(SP), .LW(LWS)) u_nc (.v(rc), .n(sigc0), .lz(lzc));
    end else begin : g_noin
        assign siga0 = ra;
        assign sigb0 = rb;
        assign sigc0 = rc;
        assign lza   = '0;
        assign lzb   = '0;
        assign lzc   = '0;
    end
    logic signed [EW-1:0] xa, xb, xc, ep0, ec0;
    assign xa  = $signed(EW'(ea == '0 ? EXP'(1) : ea)) - $signed(EW'(lza));       // the effective biased exponent of each (normalised) significand
    assign xb  = $signed(EW'(eb == '0 ? EXP'(1) : eb)) - $signed(EW'(lzb));
    assign xc  = $signed(EW'(ec == '0 ? EXP'(1) : ec)) - $signed(EW'(lzc));
    assign ep0 = xa + xb - $signed(EW'(BIAS));                                     // the product's biased exponent for a leading one at bit 2 * MAN
    assign ec0 = xc;

    logic         spv0;
    logic [W-1:0] spx0;
    always_comb begin
        spv0 = 1'b1;
        if (a_nan || b_nan || c_nan)                                spx0 = QNAN;
        else if ((a_inf && b_zero) || (b_inf && a_zero))            spx0 = QNAN;
        else if (a_inf || b_inf)                                    spx0 = (c_inf && sc != sp0) ? QNAN : {sp0, ONES, {MAN{1'b0}}};
        else if (c_inf)                                             spx0 = {sc, ONES, {MAN{1'b0}}};
        else begin
            spv0 = 1'b0;
            spx0 = '0;
        end
    end
    logic pz0, cz0;
    assign pz0 = a_zero || b_zero;
    assign cz0 = c_zero;

    // ---- rank 1 (STAGES >= 4): the multiplier's operand registers -------------------------------------------------------------
    logic                 spv1, sp1, sc1, pz1, cz1;
    logic [W-1:0]         spx1;
    logic [SP-1:0]        siga1, sigb1, sigc1;
    logic signed [EW-1:0] ep1, ec1;
    if (STAGES >= 4) begin : g_r1
        always_ff @(posedge clk) begin
            spv1 <= spv0; spx1 <= spx0; sp1 <= sp0; sc1 <= sc; pz1 <= pz0; cz1 <= cz0;
            siga1 <= siga0; sigb1 <= sigb0; sigc1 <= sigc0; ep1 <= ep0; ec1 <= ec0;
        end
    end else begin : g_n1
        assign spv1 = spv0; assign spx1 = spx0; assign sp1 = sp0; assign sc1 = sc; assign pz1 = pz0; assign cz1 = cz0;
        assign siga1 = siga0; assign sigb1 = sigb0; assign sigc1 = sigc0; assign ep1 = ep0; assign ec1 = ec0;
    end

    // ---- phase 2: the significand product ---------------------------------------------------------------------------------------
    (* use_dsp = "yes" *) logic [PW-1:0] pp2;
    assign pp2 = siga1 * sigb1;

    // ---- rank 2 (STAGES >= 3): the multiplier's product register ----------------------------------------------------------------
    logic                 spv2, sp2, sc2, pz2, cz2;
    logic [W-1:0]         spx2;
    logic [PW-1:0]        pp3;
    logic [SP-1:0]        sigc2;
    logic signed [EW-1:0] ep2, ec2;
    if (STAGES >= 3) begin : g_r2
        always_ff @(posedge clk) begin
            spv2 <= spv1; spx2 <= spx1; sp2 <= sp1; sc2 <= sc1; pz2 <= pz1; cz2 <= cz1;
            pp3 <= pp2; sigc2 <= sigc1; ep2 <= ep1; ec2 <= ec1;
        end
    end else begin : g_n2
        assign spv2 = spv1; assign spx2 = spx1; assign sp2 = sp1; assign sc2 = sc1; assign pz2 = pz1; assign cz2 = cz1;
        assign pp3 = pp2; assign sigc2 = sigc1; assign ep2 = ep1; assign ec2 = ec1;
    end

    // ---- phase 3: align, add or subtract, magnitude ------------------------------------------------------------------------------
    logic signed [EW-1:0] emp, dlt, ea3;
    assign emp = ep2 + 1;                              // the exponent of the product's nominal leading bit (bit 2 * SP - 1)
    assign dlt = emp - ec2;
    logic anchor_p;
    assign anchor_p = !pz2 && (cz2 || dlt >= 0);       // the product is the fixed operand unless it is zero, or c is larger by exponent
    assign ea3 = anchor_p ? emp : ec2;                 // the exponent of the fixed operand's leading bit (window bit WW - 2)
    logic [WW-1:0] pw, cw, sh_in, pf, cf, al;
    logic [2*WW-1:0] tsh;
    logic [EW-1:0]  amt;
    logic [WW-1:0]  al_raw;
    always_comb begin
        pw    = WW'(pp3) << (SP + 2);                  // the product's nominal leading bit at window bit WW - 2
        cw    = WW'(sigc2) << (2 * SP + 2);            // c's leading bit at window bit WW - 2
        sh_in = anchor_p ? cw : pw;
        amt = EW'(anchor_p ? dlt : -dlt);              // meaningless when the product or the addend is zero, but then the operand that is shifted is zero too
        if (amt > EW'(WW)) amt = EW'(WW);
        tsh    = {sh_in, {WW{1'b0}}} >> amt;
        al_raw = tsh[2*WW-1:WW];
        al     = {al_raw[WW-1:1], al_raw[0] | (|tsh[WW-1:0])};
        pf     = anchor_p ? pw : al;
        cf     = anchor_p ? al : cw;
    end
    logic signed [WW:0] tp, tc, tt;
    assign tp = sp2 ? -$signed({1'b0, pf}) : $signed({1'b0, pf});
    assign tc = sc2 ? -$signed({1'b0, cf}) : $signed({1'b0, cf});
    assign tt = tp + tc;
    logic          neg3, tz3, zs3;
    logic [WW-1:0] mag3;
    assign neg3 = tt[WW];
    assign mag3 = neg3 ? (~tt[WW-1:0] + {{(WW - 1){1'b0}}, 1'b1}) : tt[WW-1:0];      // |tt| < 2**WW, so the low WW bits of the two's complement negation are the magnitude
    assign tz3  = (tt == '0);
    assign zs3  = pz2 && cz2 && sp2 && sc2;            // both addends zero: the sign they share if they share it, else +0; an exact cancellation of nonzero terms is +0

    // ---- rank 3 (STAGES >= 2): between the adder and the normaliser ---------------------------------------------------------------
    logic                 spv3, neg4, tz4, zs4;
    logic [W-1:0]         spx3;
    logic [WW-1:0]        mag4;
    logic signed [EW-1:0] ea4;
    if (STAGES >= 2) begin : g_r3
        always_ff @(posedge clk) begin
            spv3 <= spv2; spx3 <= spx2; neg4 <= neg3; tz4 <= tz3; zs4 <= zs3; mag4 <= mag3; ea4 <= ea3;
        end
    end else begin : g_n3
        assign spv3 = spv2; assign spx3 = spx2; assign neg4 = neg3; assign tz4 = tz3; assign zs4 = zs3; assign mag4 = mag3; assign ea4 = ea3;
    end

    // ---- phase 4: normalise, round, pack ------------------------------------------------------------------------------------------
    logic [WW-1:0] nrm;
    logic [LW-1:0] lz;
    fp_norm #(.NW(WW), .LW(LW)) u_norm (.v(mag4), .n(nrm), .lz(lz));
    logic signed [EW-1:0] er;
    assign er = ea4 + 1 - $signed(EW'(lz));
    logic [W-1:0] packed_y;
    fp_pack #(.EXP(EXP), .MAN(MAN), .SUBNORM(SUBNORM), .NW(WW), .EW(EW)) u_pack (.sgn(neg4), .er(er), .n(nrm), .stk(1'b0), .y(packed_y));
    logic [W-1:0] y_c;
    always_comb begin
        if (spv3)      y_c = spx3;
        else if (tz4)  y_c = {zs4, {(W - 1){1'b0}}};
        else           y_c = packed_y;
    end

    // ---- rank 4 (STAGES >= 1): the output register ----------------------------------------------------------------------------------
    if (STAGES >= 1) begin : g_r4
        always_ff @(posedge clk) y <= y_c;
    end else begin : g_n4
        assign y = y_c;
    end
endmodule
