// fft_real_post: real-input FFT through an N/2-point complex FFT and post-processing (arith brief 148, variant "post").
//
// Function (arith/fft_real/spec.md): the N = 2**LOGN point DFT of a frame of N REAL samples, delivered two per clock (in_even = x[2m], in_odd = x[2m+1], signed W bits, N/2 consecutive
// clocks, the first with in_sof), as the N/2 + 1 distinct bins X[0] .. X[N/2] (the rest are the conjugates), in natural order, one bin per clock, N/2 + 1 consecutive clocks of out_valid
// (the first with out_sof). Method: z[m] = x[2m] + j x[2m+1] goes through fft_sdf_r22 of N/2 points (bit-reversed output, the core's word is W + 1 bits so a full-scale real input cannot
// overflow it); the transform Z is written into a memory at the bit-reversed address of its arrival position (so the memory is the reorder buffer); then for k = 0 .. N/2
//   E = Z[k] + conj Z[N/2-k], O = Z[k] - conj Z[N/2-k] (indices of Z modulo N/2), both shifted right by 1 (SCALE = 0) or 2 (SCALE = 1) rounded as RND says,
//   X[k] = E + W_N^k * (-j O), the product exact then shifted right by TW-2 with the same rounding.
// SCALE = 1: the output is X / N (like the complex FFT); SCALE = 0: X itself, in W + LOGN + 1 bits. Forward only.
// Rules: a frame is N/2 consecutive clocks of in_valid; the next frame starts after at least N/8 idle clocks (the read-out of a frame takes N/2 + 1 clocks, one more than the input, so
// frames cannot be back to back, and the N/2-point core needs 0 or at least N/8 idle clocks: see arith/fft/spec.md, the gap rule). Two banks of the memory, so the frame being read out is not
// overwritten by the next. Latency (in_sof to out_sof): the core's (bit-reversed) latency for N/2 points + N/2 + MULSTAGES + 3.
//
// Intended primitive use (stated before any Vivado run; not yet measured): the N/2-point core, one extra complex multiplier (3 or 4 DSP blocks), two banks of two copies of the N/2-word memory (two read
// ports) of 2 * (W + LOGN) bits, one twiddle ROM (1025 x 31), about 12 * W LUTs of adders.
module fft_real_post #(
    parameter int LOGN      = 7,
    parameter int W         = 16,
    parameter int TW        = 16,
    parameter int SCALE     = 1,
    parameter int RND       = 1,
    parameter int CMUL      = 4,
    parameter int TWSTAGES  = 1,
    parameter int MULSTAGES = 2
) (
    input  logic                                       clk,
    input  logic                                       rst,
    input  logic                                       in_valid,
    input  logic                                       in_sof,
    input  logic [W-1:0]                               in_even,
    input  logic [W-1:0]                               in_odd,
    output logic                                       out_valid,
    output logic                                       out_sof,
    output logic [((SCALE != 0) ? W + 1 : W + LOGN + 1)-1:0] out_re,
    output logic [((SCALE != 0) ? W + 1 : W + LOGN + 1)-1:0] out_im
);
    localparam int H  = 1 << (LOGN - 1);
    localparam int LH = LOGN - 1;
    localparam int WZ = (SCALE != 0) ? W + 1 : W + LOGN;        // the core's output word
    localparam int WX = (SCALE != 0) ? W + 1 : W + LOGN + 1;
    localparam int SH = 1 + SCALE;
    localparam int WE = WZ + 2;
    localparam int WA = WZ + 1;
    localparam int WP = WA + TW + 1;

    // ---- the N/2-point complex transform, bit-reversed output --------------------------------------------------------------------------
    logic signed [W-1:0] se, so;
    logic [W:0]          cre, cim;
    logic                zv, zs, unused_ready;
    logic [WZ-1:0]       zr, zi;
    always_comb begin
        se  = in_even;
        so  = in_odd;
        cre = (W + 1)'(se);
        cim = (W + 1)'(so);
    end
    fft_sdf_r22 #(.LOGN(LH), .W(W + 1), .TW(TW), .SCALE(SCALE), .RND(RND), .ORDER(1), .CMUL(CMUL), .TWSTAGES(TWSTAGES), .MULSTAGES(MULSTAGES)) u_core (
        .clk(clk), .rst(rst), .in_valid(in_valid), .in_sof(in_sof), .in_inverse(1'b0), .in_re(cre), .in_im(cim), .out_ready(1'b1), .in_ready(unused_ready),
        .out_valid(zv), .out_sof(zs), .out_re(zr), .out_im(zi));

    // ---- memory: Z written at the bit-reversed address of its arrival position ---------------------------------------------------------
    logic [2*WZ-1:0] mem_a [2*H];                               // two banks of H words: one is written while the other is read out
    logic [2*WZ-1:0] mem_b [2*H];                               // a second copy: the read-out needs Z[k] and Z[N/2-k] together
    logic [LH-1:0]   wc, wpos, wa;
    logic            last_z, wbank, rbank;
    fft_bitrev #(.LOGN(LH)) u_wrev (.a(wpos), .y(wa));
    always_comb begin
        wpos   = zs ? '0 : wc;
        last_z = zv && (wpos == LH'(H - 1));
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            wc    <= '0;
            wbank <= 1'b0;
        end else begin
            if (zv) wc <= wpos + 1'b1;
            if (last_z) wbank <= ~wbank;
        end
        if (zv) begin
            mem_a[{wbank, wa}] <= {zr, zi};
            mem_b[{wbank, wa}] <= {zr, zi};
        end
    end

    // ---- read-out: k = 0 .. N/2 --------------------------------------------------------------------------------------------------------
    logic            rd_on;
    logic [LOGN-1:0] k;
    logic [LH-1:0]   ra, rb;
    logic [2*WZ-1:0] da, db;
    logic [LOGN-1:0] kk;
    logic [TW-1:0]   wr0, wi0, wr1, wi1, wr2, wi2;
    always_comb begin
        ra = k[LH-1:0];
        rb = LH'(0) - k[LH-1:0];
        kk = k;
    end
    fft_twiddle_quarter #(.LOGC(LOGN), .TW(TW), .STAGES(TWSTAGES)) u_tw (.clk(clk), .m(kk), .wr(wr0), .wi(wi0));
    always_ff @(posedge clk) begin
        da  <= mem_a[{rbank, ra}];
        db  <= mem_b[{rbank, rb}];
        wr1 <= wr0;
        wi1 <= wi0;
        if (rst) begin
            rd_on <= 1'b0;
            k     <= '0;
        end else if (last_z) begin
            rd_on <= 1'b1;
            k     <= '0;
            rbank <= wbank;
        end else if (rd_on) begin
            k <= k + 1'b1;
            if (k == LOGN'(H)) rd_on <= 1'b0;
        end
    end
    always_comb begin
        wr2 = (TWSTAGES == 1) ? wr1 : wr0;
        wi2 = (TWSTAGES == 1) ? wi1 : wi0;
    end
    // control pipeline: issue (k), t1 (memory data), t2 (multiplier input), then MULSTAGES + 1 more
    localparam int LC = MULSTAGES + 3;
    logic [LC-1:0] v_p, s_p;
    always_ff @(posedge clk) begin
        if (rst) begin
            v_p <= '0;
            s_p <= '0;
        end else begin
            v_p <= {v_p[LC-2:0], rd_on};
            s_p <= {s_p[LC-2:0], rd_on && (k == '0)};
        end
    end

    // ---- t1: E and O ------------------------------------------------------------------------------------------------------------------
    logic signed [WZ-1:0] ar, ai, br, bi;
    // verilator lint_off UNUSEDSIGNAL
    logic signed [WE-1:0] er, ei, orr, oi, ser, sei, sor, soi;
    // verilator lint_on UNUSEDSIGNAL
    logic [WE-1:0]        rnd_c;
    always_comb begin
        {ar, ai} = da;
        {br, bi} = db;
        er  = WE'(ar) + WE'(br);
        ei  = WE'(ai) - WE'(bi);
        orr = WE'(ar) - WE'(br);
        oi  = WE'(ai) + WE'(bi);
        rnd_c = (RND != 0) ? WE'(1 << (SH - 1)) : '0;
        ser = (er + signed'(rnd_c)) >>> SH;
        sei = (ei + signed'(rnd_c)) >>> SH;
        sor = (orr + signed'(rnd_c)) >>> SH;
        soi = (oi + signed'(rnd_c)) >>> SH;
    end
    logic signed [WA-1:0] jr, ji;
    logic signed [WZ-1:0] e2r, e2i;
    logic signed [WZ-1:0] ed_r [MULSTAGES+1];
    logic signed [WZ-1:0] ed_i [MULSTAGES+1];
    always_ff @(posedge clk) begin
        jr  <= WA'(soi);                  // -j * O = (O.im, -O.re)
        ji  <= -WA'(sor);
        ed_r[0] <= WZ'(ser);
        ed_i[0] <= WZ'(sei);
        for (int s = 1; s <= MULSTAGES; s++) begin
            ed_r[s] <= ed_r[s-1];
            ed_i[s] <= ed_i[s-1];
        end
    end
    always_comb begin
        e2r = ed_r[MULSTAGES];
        e2i = ed_i[MULSTAGES];
    end

    // ---- t2: twiddle product, rounded; X = E + product -----------------------------------------------------------------------------------
    logic [WP-1:0] pr, pi;
    generate
        if (CMUL == 3) begin : g_m3
            fft_cmul_m3 #(.WA(WA), .WB(TW), .STAGES(MULSTAGES)) u_m (.clk(clk), .ar(jr), .ai(ji), .br(wr2), .bi(wi2), .pr(pr), .pi(pi));
        end else begin : g_m4
            fft_cmul_m4 #(.WA(WA), .WB(TW), .STAGES(MULSTAGES)) u_m (.clk(clk), .ar(jr), .ai(ji), .br(wr2), .bi(wi2), .pr(pr), .pi(pi));
        end
    endgenerate
    // verilator lint_off UNUSEDSIGNAL
    logic signed [WP-1:0] spr, spi, rr, ri;
    // verilator lint_on UNUSEDSIGNAL
    logic [WX-1:0] xr_q, xi_q;
    always_comb begin
        spr = pr;
        spi = pi;
        rr = (RND != 0) ? (spr + (WP)'(1 << (TW - 3))) >>> (TW - 2) : spr >>> (TW - 2);
        ri = (RND != 0) ? (spi + (WP)'(1 << (TW - 3))) >>> (TW - 2) : spi >>> (TW - 2);
    end
    always_ff @(posedge clk) begin
        xr_q <= WX'(e2r) + WX'(rr);
        xi_q <= WX'(e2i) + WX'(ri);
    end
    always_comb begin
        out_valid = v_p[LC-1];
        out_sof   = s_p[LC-1];
        out_re    = xr_q;
        out_im    = xi_q;
    end
endmodule
