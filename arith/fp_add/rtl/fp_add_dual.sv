// fp_add_dual: floating-point adder with a near path and a far path (arith brief 139e, variant "dual_path").
//
// Function (arith/fp_add/spec.md): y = a + b, the same function, ports and parameters as fp_add_single (EXP, MAN, SUBNORM, STAGES; latency STAGES, one sum per clock, round to
// nearest even, canonical quiet NaN, no flags, no reset). The structure differs: after ordering the operands by magnitude, two datapaths run side by side and the result of one is
// selected just before rounding.
//   far path  (an effective addition, or a subtraction with exponents more than 1 apart): the full-width aligner and an adder; the sum can need at most a 2-place left
//             shift to normalise (3-way multiplexer, no leading-zero count);
//   near path (a subtraction with exponents at most 1 apart, or both operands subnormal): a 1-place alignment (exact, no sticky bit), an adder, and the full leading-zero count and
//             left shift, because massive cancellation can need any shift.
// No single path has both a full-width aligner and a full-width normaliser; that is the shorter longest path. The cost is a second adder, a second SP + 4 bit register in each
// rank and the extra small shifter.
//
// Intended primitive use (stated before any Vivado run; not yet measured): LUTs and carry chains only, no DSP and no block RAM. Roughly one SP + 3 bit barrel shifter (far
// aligner), one full-width normaliser (near path only), two SP + 4 bit adder/subtractors on carry chains, a 3-way small shifter, a 2-way selector, and the rounding incrementer;
// flip-flops only for the rank registers (STAGES), about a third more bits per rank than fp_add_single. With SUBNORM = 1 an extra right shifter denormalises small results (fp_pack).
module fp_add_dual #(
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
    localparam int NS  = SP + 3;                       // aligned significand: SP bits plus guard, round, sticky
    localparam int WS  = NS + 1;                       // the sum, with its carry bit
    localparam int LW  = $clog2(WS) + 1;
    localparam int EW  = (EXP > $clog2(WS + 4) ? EXP : $clog2(WS + 4)) + 2;
    localparam logic [EXP-1:0] ONES = '1;
    localparam logic [W-1:0]   QNAN = {1'b0, ONES, 1'b1, {(MAN - 1){1'b0}}};

    // ---- phase 1: unpack, special cases, order by magnitude, align ----------------------------------------------------------
    logic sa, sb;
    logic [EXP-1:0] ea, eb;
    logic [MAN-1:0] fa, fb;
    assign {sa, ea, fa} = a;
    assign {sb, eb, fb} = b;
    logic a_nan, b_nan, a_inf, b_inf;
    assign a_nan = (ea == ONES) && (fa != '0);
    assign b_nan = (eb == ONES) && (fb != '0);
    assign a_inf = (ea == ONES) && (fa == '0);
    assign b_inf = (eb == ONES) && (fb == '0);

    logic [EXP+MAN-1:0] ma, mb;                        // magnitudes with a subnormal flushed to zero when SUBNORM = 0
    assign ma = (SUBNORM == 0 && ea == '0) ? '0 : a[EXP+MAN-1:0];
    assign mb = (SUBNORM == 0 && eb == '0) ? '0 : b[EXP+MAN-1:0];
    logic a_ge;
    assign a_ge = ma >= mb;
    logic           sx, sy;
    logic [EXP+MAN-1:0] mx, my;
    assign sx = a_ge ? sa : sb;
    assign sy = a_ge ? sb : sa;
    assign mx = a_ge ? ma : mb;
    assign my = a_ge ? mb : ma;
    logic [EXP-1:0] erx, ery, ex, ey, d;
    assign erx = mx[EXP+MAN-1:MAN];
    assign ery = my[EXP+MAN-1:MAN];
    assign ex  = (erx == '0) ? EXP'(1) : erx;           // effective exponent: a subnormal has exponent 1 and no hidden bit
    assign ey  = (ery == '0) ? EXP'(1) : ery;
    assign d   = ex - ey;
    logic [SP-1:0] sigx, sigy;
    assign sigx = {(erx != '0), mx[MAN-1:0]};
    assign sigy = {(ery != '0), my[MAN-1:0]};
    logic esub0;
    assign esub0 = sx ^ sy;

    logic [NS-1:0]    x0, yal0, ynr0;
    logic             near0;
    logic [2*NS-1:0]  tsh;
    logic [EW-1:0]    dc;
    always_comb begin
        dc   = (EW'(d) > EW'(NS)) ? EW'(NS) : EW'(d);
        x0   = {sigx, 3'b000};
        tsh  = {sigy, 3'b000, {NS{1'b0}}} >> dc;
        yal0 = {tsh[2*NS-1:NS+1], tsh[NS] | (|tsh[NS-1:0])};
        ynr0 = (d == EXP'(1)) ? ({sigy, 3'b000} >> 1) : {sigy, 3'b000};               // exact: the three low bits are zero before the shift
    end
    assign near0 = (esub0 && d <= EXP'(1)) || (erx == '0);                             // cancellation is possible, or both operands are subnormal

    logic         sp_v0;                               // a special result (NaN, infinity) overrides the datapath
    logic [W-1:0] sp_x0;
    always_comb begin
        sp_v0 = 1'b1;
        if (a_nan || b_nan)                    sp_x0 = QNAN;
        else if (a_inf && b_inf && sa != sb)   sp_x0 = QNAN;
        else if (a_inf)                        sp_x0 = {sa, ONES, {MAN{1'b0}}};
        else if (b_inf)                        sp_x0 = {sb, ONES, {MAN{1'b0}}};
        else begin
            sp_v0 = 1'b0;
            sp_x0 = '0;
        end
    end

    // ---- rank 1 -------------------------------------------------------------------------------------------------------------
    logic           sp_v1, sx1, es1, nr1;
    logic [W-1:0]   sp_x1;
    logic [EXP-1:0] ex1;
    logic [NS-1:0]  x1, y1, yn1;
    if (STAGES >= 2) begin : g_r1
        always_ff @(posedge clk) begin
            sp_v1 <= sp_v0;
            sp_x1 <= sp_x0;
            sx1   <= sx;
            es1   <= esub0;
            nr1   <= near0;
            ex1   <= ex;
            x1    <= x0;
            y1    <= yal0;
            yn1   <= ynr0;
        end
    end else begin : g_n1
        assign sp_v1 = sp_v0;
        assign sp_x1 = sp_x0;
        assign sx1   = sx;
        assign es1   = esub0;
        assign nr1   = near0;
        assign ex1   = ex;
        assign x1    = x0;
        assign y1    = yal0;
        assign yn1   = ynr0;
    end

    // ---- phase 2: add or subtract -------------------------------------------------------------------------------------------
    logic [WS-1:0] sf2, sn2;
    assign sf2 = es1 ? ({1'b0, x1} - {1'b0, y1})  : ({1'b0, x1} + {1'b0, y1});         // far path
    assign sn2 = es1 ? ({1'b0, x1} - {1'b0, yn1}) : ({1'b0, x1} + {1'b0, yn1});        // near path

    // ---- rank 2 -------------------------------------------------------------------------------------------------------------
    logic           sp_v2, sx2, es2, nr2;
    logic [W-1:0]   sp_x2;
    logic [EXP-1:0] ex2;
    logic [WS-1:0]  sf3, sn3;
    if (STAGES >= 3) begin : g_r2
        always_ff @(posedge clk) begin
            sp_v2 <= sp_v1;
            sp_x2 <= sp_x1;
            sx2   <= sx1;
            es2   <= es1;
            nr2   <= nr1;
            ex2   <= ex1;
            sf3   <= sf2;
            sn3   <= sn2;
        end
    end else begin : g_n2
        assign sp_v2 = sp_v1;
        assign sp_x2 = sp_x1;
        assign sx2   = sx1;
        assign es2   = es1;
        assign nr2   = nr1;
        assign ex2   = ex1;
        assign sf3   = sf2;
        assign sn3   = sn2;
    end

    // ---- phase 3: normalise (near: full count; far: at most two places), select, round, pack ------------------------------------
    logic [WS-1:0] nrm_n, nrm_f, nrm;
    logic [LW-1:0] lz_n;
    fp_norm #(.NW(WS), .LW(LW)) u_norm (.v(sn3), .n(nrm_n), .lz(lz_n));
    logic [1:0] lz_f;
    always_comb begin
        if (sf3[WS-1])      begin lz_f = 2'd0; nrm_f = sf3;      end
        else if (sf3[WS-2]) begin lz_f = 2'd1; nrm_f = sf3 << 1; end
        else                begin lz_f = 2'd2; nrm_f = sf3 << 2; end
    end
    logic [LW-1:0] lz;
    assign nrm = nr2 ? nrm_n : nrm_f;
    assign lz  = nr2 ? lz_n : {{(LW - 2){1'b0}}, lz_f};
    logic signed [EW-1:0] er;
    assign er = $signed(EW'(ex2)) + 1 - $signed(EW'(lz));
    logic [W-1:0] packed_y;
    fp_pack #(.EXP(EXP), .MAN(MAN), .SUBNORM(SUBNORM), .NW(WS), .EW(EW)) u_pack (.sgn(sx2), .er(er), .n(nrm), .stk(1'b0), .y(packed_y));
    logic [W-1:0] y_c;
    always_comb begin
        if (sp_v2)           y_c = sp_x2;
        else if ((nr2 ? sn3 : sf3) == '0)   y_c = {(es2 ? 1'b0 : sx2), {(W - 1){1'b0}}};          // an exact zero sum: +0 unless both operands are -0
        else                 y_c = packed_y;
    end

    // ---- rank 3: the output register ----------------------------------------------------------------------------------------
    if (STAGES >= 1) begin : g_r3
        always_ff @(posedge clk) y <= y_c;
    end else begin : g_n3
        assign y = y_c;
    end
endmodule
