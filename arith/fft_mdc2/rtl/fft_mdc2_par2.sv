// fft_mdc2_par2: 2-parallel streaming FFT, two complex samples per clock (arith brief 161, variant "par2").
//
// Function (arith/fft_mdc2/spec.md): the N = 2**LOGN point DFT of each frame of N complex samples, delivered as N/2 clocks of a PAIR of consecutive samples (x[2m], x[2m+1]) at clock m,
// forward or (swap trick, in_inverse sampled with in_sof) inverse, scaled by 1/N (SCALE = 1, W bits) or growing (SCALE = 0, W + LOGN bits).
// Architecture: the even samples and the odd samples go through two N/2-point radix-2^2 single-path delay-feedback pipelines (fft_sdf_r22, one sample per clock each), and one more radix-2
// stage, shared by the two paths, combines them: X[k] = E[k] + W_N^k O[k] and X[k + N/2] = E[k] - W_N^k O[k] (the product rounded once, the sum and difference halved when scaled). The
// output at clock k is the pair (X[k], X[k + N/2]); with ORDER = 1 the sub-pipelines emit bit-reversed order and the pair at clock p is (X[b], X[b + N/2]) for b = the bit reversal of p in LOGN - 1 bits.
// This is a 2-parallel pipelined transform with the throughput and the delay-memory count of a radix-2^2 multi-path delay commutator; its structure is the decimation-in-time split, not the
// commutator (docs/fft_suite_plan.md section 2): its multipliers are 2 * ((LOGN - 2) // 2) in the two sub-pipelines plus 1 in the combining stage.
//
// Streaming rules (those of the N/2-point sdf sub-pipelines): a frame is N/2 consecutive clocks of in_valid, the first with in_sof; the next frame follows with no gap or after at least N/8 idle clocks
// (a gap of 1 to N/8 - 1 is not allowed); in_ready is always 1; there is no back-pressure: the consumer must take every output pair when it is presented (out_valid is N/2 consecutive clocks).
// Latency (in_sof to out_sof): sub-pipeline latency (N/2 - 1 + (LOGN - 1) + ((LOGN - 2) // 2) * LMUL, plus N/2 + 1 for ORDER = 0) plus LMUL + 1, with LMUL = TWSTAGES + MULSTAGES + 1.
//
// Intended primitive use (stated before any Vivado run; not yet measured): two N/2-point sdf pipelines (each about N/2 - 1 words of delay memory and (LOGN - 2) // 2 complex multipliers: for
// N = 1024, W = TW = 16, CMUL 4: 8 complex multipliers in all), plus one complex multiplier (3 or 4 DSP), the twiddle ROM and about 6 * W LUTs for the final butterfly.
module fft_mdc2_par2 #(
    parameter int LOGN      = 6,
    parameter int W         = 16,
    parameter int TW        = 16,
    parameter int SCALE     = 1,
    parameter int RND       = 1,
    parameter int ORDER     = 0,
    parameter int CMUL      = 4,
    parameter int TWSTAGES  = 1,
    parameter int MULSTAGES = 2
) (
    input  logic                                       clk,
    input  logic                                       rst,
    input  logic                                       in_valid,
    input  logic                                       in_sof,
    input  logic                                       in_inverse,
    input  logic [W-1:0]                               in_re0,
    input  logic [W-1:0]                               in_im0,
    input  logic [W-1:0]                               in_re1,
    input  logic [W-1:0]                               in_im1,
    output logic                                       in_ready,
    output logic                                       out_valid,
    output logic                                       out_sof,
    output logic [((SCALE != 0) ? W : W + LOGN)-1:0]   out_re0,
    output logic [((SCALE != 0) ? W : W + LOGN)-1:0]   out_im0,
    output logic [((SCALE != 0) ? W : W + LOGN)-1:0]   out_re1,
    output logic [((SCALE != 0) ? W : W + LOGN)-1:0]   out_im1
);
    localparam int N     = 1 << LOGN;
    localparam int H     = N / 2;
    localparam int WS    = (SCALE != 0) ? W : W + LOGN - 1;       // sub-pipeline output width
    localparam int WO    = (SCALE != 0) ? W : W + LOGN;
    localparam int LMUL  = TWSTAGES + MULSTAGES + 1;
    localparam int LP    = LMUL;                                  // clocks from a sub-pipeline output to the rounded product register
    localparam int LC    = LMUL + 1;                              // ... to the output registers
    localparam int WP    = WS + TW + 1;
    // latency of an N/2-point sdf pipeline (arith/fft/spec.md, sdf)
    localparam int LSUB  = H - 1 + (LOGN - 1) + ((LOGN - 2) / 2) * LMUL + ((ORDER != 0) ? 0 : H + 1);
    localparam int LCH   = LSUB + LC - 1;                         // delay of the direction flag to the clock before the output registers

    assign in_ready = 1'b1;

    // ---- input: direction sampled with in_sof, swap of the real and imaginary parts for an inverse transform ------------------------------------
    logic inv_q, inv_eff;
    logic signed [W-1:0] a0r, a0i, a1r, a1i;
    always_comb begin
        inv_eff = in_sof ? in_inverse : inv_q;
        a0r = inv_eff ? in_im0 : in_re0;
        a0i = inv_eff ? in_re0 : in_im0;
        a1r = inv_eff ? in_im1 : in_re1;
        a1i = inv_eff ? in_re1 : in_im1;
    end
    logic [LCH-1:0] invc;
    always_ff @(posedge clk) begin
        if (rst) begin
            inv_q <= 1'b0;
            invc  <= '0;
        end else begin
            invc <= {invc[LCH-2:0], in_inverse};
            if (in_valid) inv_q <= inv_eff;
        end
    end

    // ---- the two N/2-point sub-pipelines: even samples and odd samples -------------------------------------------------------------------------
    logic          ev_valid, ev_sof, od_valid, od_sof;
    logic [WS-1:0] er, ei, or_, oi;
    // verilator lint_off UNUSEDSIGNAL
    logic          ev_ready, od_ready, od_v_unused, od_s_unused;
    // verilator lint_on UNUSEDSIGNAL
    fft_sdf_r22 #(.LOGN(LOGN - 1), .W(W), .TW(TW), .SCALE(SCALE), .RND(RND), .ORDER(ORDER), .CMUL(CMUL), .TWSTAGES(TWSTAGES), .MULSTAGES(MULSTAGES)) u_even (
        .clk(clk), .rst(rst), .in_valid(in_valid), .in_sof(in_sof), .in_inverse(1'b0), .in_re(a0r), .in_im(a0i), .out_ready(1'b1),
        .in_ready(ev_ready), .out_valid(ev_valid), .out_sof(ev_sof), .out_re(er), .out_im(ei));
    fft_sdf_r22 #(.LOGN(LOGN - 1), .W(W), .TW(TW), .SCALE(SCALE), .RND(RND), .ORDER(ORDER), .CMUL(CMUL), .TWSTAGES(TWSTAGES), .MULSTAGES(MULSTAGES)) u_odd (
        .clk(clk), .rst(rst), .in_valid(in_valid), .in_sof(in_sof), .in_inverse(1'b0), .in_re(a1r), .in_im(a1i), .out_ready(1'b1),
        .in_ready(od_ready), .out_valid(od_valid), .out_sof(od_sof), .out_re(or_), .out_im(oi));
    always_comb begin
        od_v_unused = od_valid;                      // the odd pipeline runs in lockstep with the even one: its control equals the even one's
        od_s_unused = od_sof;
    end

    // ---- twiddle index: the position of the word in the sub-pipeline's output order -------------------------------------------------------------
    logic [LOGN-2:0] cnt, pos, kk, pbr;
    logic [LOGN-1:0] m;
    always_comb begin
        pos = ev_sof ? '0 : cnt;
        for (int i = 0; i < LOGN - 1; i++) pbr[i] = pos[LOGN-2-i];
        kk  = (ORDER != 0) ? pbr : pos;
        m   = {1'b0, kk};
    end
    always_ff @(posedge clk) begin
        if (rst) cnt <= '0;
        else if (ev_valid) cnt <= pos + 1'b1;
    end
    logic [TW-1:0] wr, wi;
    fft_twiddle_quarter #(.LOGC(LOGN), .TW(TW), .STAGES(TWSTAGES)) u_tw (.clk(clk), .m(m), .wr(wr), .wi(wi));

    // ---- the odd path: delay to meet the twiddle, complex multiply (exact), rounded shift, register -----------------------------------------------
    logic [WS-1:0] dr [TWSTAGES];
    logic [WS-1:0] di [TWSTAGES];
    always_ff @(posedge clk) begin
        dr[0] <= or_;
        di[0] <= oi;
        for (int s = 1; s < TWSTAGES; s++) begin
            dr[s] <= dr[s-1];
            di[s] <= di[s-1];
        end
    end
    logic [WP-1:0] pr, pi;
    generate
        if (CMUL == 3) begin : g_m3
            fft_cmul_m3 #(.WA(WS), .WB(TW), .STAGES(MULSTAGES)) u_m (.clk(clk), .ar(dr[TWSTAGES-1]), .ai(di[TWSTAGES-1]), .br(wr), .bi(wi), .pr(pr), .pi(pi));
        end else begin : g_m4
            fft_cmul_m4 #(.WA(WS), .WB(TW), .STAGES(MULSTAGES)) u_m (.clk(clk), .ar(dr[TWSTAGES-1]), .ai(di[TWSTAGES-1]), .br(wr), .bi(wi), .pr(pr), .pi(pi));
        end
    endgenerate
    // verilator lint_off UNUSEDSIGNAL
    logic signed [WP-1:0] sr, si, rr, ri;
    // verilator lint_on UNUSEDSIGNAL
    logic signed [WS-1:0] qr, qi;
    always_comb begin
        sr = pr;
        si = pi;
        rr = (RND != 0) ? (sr + (WP)'(1 << (TW - 3))) >>> (TW - 2) : sr >>> (TW - 2);
        ri = (RND != 0) ? (si + (WP)'(1 << (TW - 3))) >>> (TW - 2) : si >>> (TW - 2);
    end
    always_ff @(posedge clk) begin
        qr <= WS'(rr);
        qi <= WS'(ri);
    end

    // ---- the even path: delayed by the same LP clocks ------------------------------------------------------------------------------------------
    logic [WS-1:0] xr_d [LP];
    logic [WS-1:0] xi_d [LP];
    always_ff @(posedge clk) begin
        xr_d[0] <= er;
        xi_d[0] <= ei;
        for (int s = 1; s < LP; s++) begin
            xr_d[s] <= xr_d[s-1];
            xi_d[s] <= xi_d[s-1];
        end
    end

    // ---- control: valid and start of frame delayed with the data; the direction flag of the frame ---------------------------------------------------
    logic [LC-1:0] vv, sv;
    always_ff @(posedge clk) begin
        if (rst) begin
            vv <= '0;
            sv <= '0;
        end else begin
            vv <= {vv[LC-2:0], ev_valid};
            sv <= {sv[LC-2:0], ev_valid && ev_sof};
        end
    end
    logic sof_in, v_in, inv_f, inv_h;
    always_comb begin
        v_in   = vv[LC-2];                                   // the clock before the output registers
        sof_in = sv[LC-2];
        inv_f  = sof_in ? invc[LCH-1] : inv_h;
    end
    always_ff @(posedge clk) begin
        if (rst) inv_h <= 1'b0;
        else if (v_in) inv_h <= inv_f;
    end

    // ---- the combining butterfly: X[k] = E + P, X[k + N/2] = E - P, halved when scaled ---------------------------------------------------------------
    logic signed [WS:0] s_r, s_i, d_r, d_i;
    logic signed [WO-1:0] t_r, t_i, u_r, u_i;
    always_comb begin
        s_r = (WS + 1)'($signed(xr_d[LP-1])) + (WS + 1)'(qr);
        s_i = (WS + 1)'($signed(xi_d[LP-1])) + (WS + 1)'(qi);
        d_r = (WS + 1)'($signed(xr_d[LP-1])) - (WS + 1)'(qr);
        d_i = (WS + 1)'($signed(xi_d[LP-1])) - (WS + 1)'(qi);
        if (SCALE != 0) begin
            t_r = WO'((RND != 0) ? (s_r + (WS + 1)'(1)) >>> 1 : s_r >>> 1);
            t_i = WO'((RND != 0) ? (s_i + (WS + 1)'(1)) >>> 1 : s_i >>> 1);
            u_r = WO'((RND != 0) ? (d_r + (WS + 1)'(1)) >>> 1 : d_r >>> 1);
            u_i = WO'((RND != 0) ? (d_i + (WS + 1)'(1)) >>> 1 : d_i >>> 1);
        end else begin
            t_r = WO'(s_r);
            t_i = WO'(s_i);
            u_r = WO'(d_r);
            u_i = WO'(d_i);
        end
    end
    always_ff @(posedge clk) begin
        out_re0 <= inv_f ? t_i : t_r;
        out_im0 <= inv_f ? t_r : t_i;
        out_re1 <= inv_f ? u_i : u_r;
        out_im1 <= inv_f ? u_r : u_i;
    end
    assign out_valid = vv[LC-1];
    assign out_sof   = sv[LC-1];
endmodule
