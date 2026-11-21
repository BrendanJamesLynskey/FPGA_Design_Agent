// fft_sdf_r22: streaming FFT, radix-2^2 single-path delay feedback, one complex sample per clock (arith brief 148, variant "sdf").
//
// Function (arith/fft/spec.md): the N = 2**LOGN point DFT of each frame of N complex samples (in_re, in_im signed W bits), forward (X[k] = sum x[n] exp(-j 2 pi n k / N))
// or, with in_inverse sampled at in_sof, inverse (exp(+j ...)) by swapping the real and imaginary parts around a forward transform. SCALE = 1 halves every butterfly sum and
// difference (the whole transform is scaled by 1/N in both directions, the word stays W bits); SCALE = 0 is unscaled (the word grows one bit per butterfly stage, W + LOGN bits out).
// ORDER = 0: natural-order output (a ping-pong reorder buffer follows, +N+1 clocks); ORDER = 1: bit-reversed output (the natural result of the decimation-in-frequency flow).
//
// Streaming rules: a frame is N consecutive clocks of in_valid, the first with in_sof; the next frame follows with no gap, or after at least N/4 idle clocks (a gap of 1 .. N/4 - 1
// clocks is not allowed: the position counter of the stage that feeds the first twiddle multiplier restarts while that stage still drains; measured, spec.md). The outputs are N consecutive clocks of out_valid, the first with out_sof. in_ready is always 1, and out_ready is IGNORED: this variant cannot be stalled (no back-pressure), the consumer must take every output word in the clock it is presented.
// Latency (in_sof to out_sof): ORDER = 1: N - 1 + LOGN + NM * (TWSTAGES + MULSTAGES + 1); ORDER = 0: that + N + 1; NM = (LOGN - 1) / 2 twiddle multipliers.
//
// Intended primitive use (stated before any Vivado run; not yet measured): the feedback delay lines are about N - 1 words of 2 * W..(W + LOGN) bits in all (shift registers or block
// RAM for the long ones), NM complex multipliers (3 or 4 DSP blocks each, CMUL), twiddle ROMs of 1025 x 31 bits (one per multiplier), and the control delay line of 2 * (latency) flip-flops
// (reset, so it is not an SRL): about 2.1 k flip-flops at N = 1024 and 8.2 k at N = 4096, a known cost to be replaced by counters if the measurement says it matters.
module fft_sdf_r22 #(
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
    input  logic [W-1:0]                               in_re,
    input  logic [W-1:0]                               in_im,
    // verilator lint_off UNUSEDSIGNAL
    input  logic                                       out_ready,
    // verilator lint_on UNUSEDSIGNAL
    output logic                                       in_ready,
    output logic                                       out_valid,
    output logic                                       out_sof,
    output logic [((SCALE != 0) ? W : W + LOGN)-1:0]   out_re,
    output logic [((SCALE != 0) ? W : W + LOGN)-1:0]   out_im
);
    localparam int N    = 1 << LOGN;
    localparam int WOUT = (SCALE != 0) ? W : W + LOGN;
    localparam int LMUL = TWSTAGES + MULSTAGES + 1;

    // clocks from in_sof to the sof at the input of stage s (stage s of 0 .. LOGN - 1), and to the output of the last stage (s = LOGN)
    function automatic int lat_to(input int s);
        int a;
        a = 0;
        for (int k = 0; k < s; k++) begin
            a += (1 << (LOGN - k - 1)) + 1;
            if ((k % 2 == 1) && (k <= LOGN - 2)) a += LMUL;
        end
        return a;
    endfunction
    function automatic int wd(input int s);          // data width after s butterfly stages
        return (SCALE != 0) ? W : W + s;
    endfunction
    localparam int LTOT = lat_to(LOGN);

    assign in_ready = 1'b1;

    // ---- control: the start-of-frame marker and the direction flag travel on a delay line; the stages' counters restart on it --------------
    logic [LTOT-1:0] sofc, invc;
    logic            inv_q, inv_eff, sof0;
    always_comb begin
        sof0    = in_valid && in_sof;
        inv_eff = in_sof ? in_inverse : inv_q;
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            sofc  <= '0;
            invc  <= '0;
            inv_q <= 1'b0;
        end else begin
            sofc <= {sofc[LTOT-2:0], sof0};
            invc <= {invc[LTOT-2:0], in_inverse};
            if (in_valid) inv_q <= inv_eff;
        end
    end

    // ---- the data path ----------------------------------------------------------------------------------------------------------------
    // verilator lint_off UNUSEDSIGNAL
    logic [WOUT-1:0] bus_r [LOGN+1];
    logic [WOUT-1:0] bus_i [LOGN+1];
    // verilator lint_on UNUSEDSIGNAL
    logic signed [W-1:0] x0r, x0i;
    always_comb begin
        x0r = inv_eff ? in_im : in_re;
        x0i = inv_eff ? in_re : in_im;
        bus_r[0] = WOUT'(x0r);
        bus_i[0] = WOUT'(x0i);
    end
    generate
        for (genvar s = 0; s < LOGN; s++) begin : g_st
            localparam int WI    = wd(s);
            localparam int WS    = (SCALE != 0) ? WI : WI + 1;
            localparam bit HASM  = (s % 2 == 1) && (s <= LOGN - 2);
            logic sof_s;
            if (s == 0) begin : g_s0
                assign sof_s = sof0;
            end else begin : g_sn
                assign sof_s = sofc[lat_to(s)-1];
            end
            logic [WS-1:0]   yr, yi;
            logic [LOGN-1:0] pos;
            fft_sdf_stage #(.LOGN(LOGN), .LD(LOGN - s - 1), .TYP(s % 2), .WI(WI), .SCALE(SCALE), .RND(RND)) u_st (
                .clk(clk), .sof(sof_s), .xr(bus_r[s][WI-1:0]), .xi(bus_i[s][WI-1:0]), .yr(yr), .yi(yi), .pos(pos));
            logic signed [WS-1:0] zr, zi;
            if (HASM) begin : g_m
                fft_sdf_twmul #(.LOGN(LOGN), .LM(LOGN - s + 1), .W(WS), .TW(TW), .RND(RND), .CMUL(CMUL), .TWSTAGES(TWSTAGES), .MULSTAGES(MULSTAGES)) u_m (
                    .clk(clk), .pos(pos), .xr(yr), .xi(yi), .yr(zr), .yi(zi));
            end else begin : g_nm
                // verilator lint_off UNUSEDSIGNAL
                logic [LOGN-1:0] unused_pos;
                // verilator lint_on UNUSEDSIGNAL
                assign unused_pos = pos;
                assign zr = yr;
                assign zi = yi;
            end
            assign bus_r[s+1] = WOUT'(zr);
            assign bus_i[s+1] = WOUT'(zi);
        end
    endgenerate

    // ---- output: frame window, direction swap, optional natural-order reorder -------------------------------------------------------
    logic            sof_o, inv_o, inv_h, v_o;
    logic [LOGN-1:0] rem;
    always_comb begin
        sof_o = sofc[LTOT-1];
        inv_o = sof_o ? invc[LTOT-1] : inv_h;
        v_o   = sof_o || (rem != '0);
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            rem   <= '0;
            inv_h <= 1'b0;
        end else begin
            inv_h <= inv_o;
            if (sof_o) rem <= LOGN'(N - 1);
            else if (rem != '0) rem <= rem - 1'b1;
        end
    end
    logic [WOUT-1:0] br_r, br_i;
    always_comb begin
        br_r = inv_o ? bus_i[LOGN] : bus_r[LOGN];
        br_i = inv_o ? bus_r[LOGN] : bus_i[LOGN];
    end
    generate
        if (ORDER == 0) begin : g_nat
            logic [2*WOUT-1:0] rd;
            fft_reorder_pingpong #(.LOGN(LOGN), .WD(2 * WOUT)) u_ro (.clk(clk), .rst(rst), .in_valid(v_o), .in_sof(sof_o), .in_d({br_r, br_i}),
                                                                       .out_valid(out_valid), .out_sof(out_sof), .out_d(rd));
            assign out_re = rd[2*WOUT-1:WOUT];
            assign out_im = rd[WOUT-1:0];
        end else begin : g_br
            assign out_valid = v_o;
            assign out_sof   = sof_o;
            assign out_re    = br_r;
            assign out_im    = br_i;
        end
    endgenerate
endmodule
