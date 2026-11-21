// fft_burst_r2: memory-based burst FFT, one radix-2 butterfly, in-place two-bank memory (arith brief 148, variant "burst").
//
// Function (arith/fft/spec.md): the same transform, parameters, scaling, direction and output orders as fft_sdf_r22; the bits differ because the rounding points differ (every
// butterfly's difference is multiplied by its twiddle, rounded; the model is fft_ref.burst_frame). One frame at a time: the frame is loaded (N consecutive clocks of in_valid, the first
// with in_sof, only when in_ready is 1), then LOGN radix-2 decimation-in-frequency stages run on one butterfly (one pair per clock, then LP clocks of pipeline drain between stages),
// then the N results are read out in N consecutive clocks (ORDER = 0: natural order, read in bit-reversed address order; ORDER = 1: bit-reversed order, read in address order).
// in_ready is 1 only while idle and with no output word waiting (it falls in the clock after in_sof and rises one clock after the last output word has been taken). out_ready is honoured: the unload stalls while out_ready is low, with out_valid, out_sof and the data held. Latency (in_sof to out_sof): N + LOGN * (N / 2 + LP) + 1, LP = MULSTAGES + 3.
//
// Memory: two banks by the parity of the word address, so the two words of a butterfly (addresses differing in one bit) are always in different banks: each bank has one read and
// one write port, N / 2 words of 2 * WM bits (WM = W for SCALE = 1, W + LOGN for SCALE = 0). The butterfly pipeline: read (1), add/subtract (1), twiddle multiply (MULSTAGES + 1).
//
// Intended primitive use (stated before any Vivado run; not yet measured): 2 banks of N/2 x 2 * WM bits (block RAM for N >= 256: for W = 16 about 16 Kbit per bank at N = 512, so one
// RAMB18 each; distributed RAM below that), one complex multiplier (3 or 4 DSP blocks, CMUL), one twiddle ROM (1025 x 31), about 8 * WM LUTs for the butterfly and a few hundred LUTs of control.
module fft_burst_r2 #(
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
    input  logic                                       out_ready,
    output logic                                       in_ready,
    output logic                                       out_valid,
    output logic                                       out_sof,
    output logic [((SCALE != 0) ? W : W + LOGN)-1:0]   out_re,
    output logic [((SCALE != 0) ? W : W + LOGN)-1:0]   out_im
);
    localparam int N  = 1 << LOGN;
    localparam int WM = (SCALE != 0) ? W : W + LOGN;
    localparam int LP = MULSTAGES + 3;
    localparam int CW = LOGN + 4;
    localparam int WP = WM + TW + 1;

    typedef enum logic [1:0] {S_IDLE, S_LOAD, S_COMP, S_UNLD} state_t;
    state_t          state;
    logic [LOGN-1:0] lc, oc;
    logic [3:0]      st;
    logic [CW-1:0]   cyc;
    logic            inv_f;
    logic ov, os_q, ob;
    logic adv;                                   // the output register is free or being consumed: the unload may advance
    assign adv      = !ov || out_ready;
    assign in_ready = (state == S_IDLE) && !ov;

    // ---- memory -----------------------------------------------------------------------------------------------------------------------
    logic [2*WM-1:0] mem0 [N/2];
    logic [2*WM-1:0] mem1 [N/2];
    logic [2*WM-1:0] rd0, rd1;
    logic            we0, we1;
    logic [LOGN-2:0] wa0, wa1, ra0, ra1;
    logic [2*WM-1:0] wd0, wd1;
    always_ff @(posedge clk) begin
        if (we0) mem0[wa0] <= wd0;
        if (we1) mem1[wa1] <= wd1;
        if (!(ov && !out_ready)) begin               // held while an output word waits for out_ready
            rd0 <= mem0[ra0];
            rd1 <= mem1[ra1];
        end
    end

    // ---- load -------------------------------------------------------------------------------------------------------------------------
    logic            ld_we, inv_eff, ld_par;
    logic [LOGN-1:0] ld_pos;
    logic signed [W-1:0] ldr, ldi;
    logic [2*WM-1:0] ld_d;
    always_comb begin
        ld_we   = in_valid && ((state == S_IDLE && in_sof) || state == S_LOAD);
        ld_pos  = (state == S_IDLE) ? '0 : lc;
        inv_eff = (state == S_IDLE) ? in_inverse : inv_f;
        ldr     = inv_eff ? in_im : in_re;
        ldi     = inv_eff ? in_re : in_im;
        ld_d    = {WM'(ldr), WM'(ldi)};
        ld_par  = ^ld_pos;
    end

    // ---- butterfly issue (clock t0) ---------------------------------------------------------------------------------------------------
    logic            issue;
    // verilator lint_off UNUSEDSIGNAL
    logic [LOGN-1:0] j, a, b, h, mask, tm;      // bit 0 of b (the in-bank address drops it) is not used
    // verilator lint_on UNUSEDSIGNAL
    logic [3:0]      hl;
    logic            pa;
    logic [LOGN-2:0] ia, ib;
    always_comb begin
        issue = (state == S_COMP) && (cyc < CW'(N / 2));
        j     = LOGN'(cyc);
        hl    = 4'(LOGN - 1) - st;
        h     = LOGN'(1) << hl;
        mask  = h - 1'b1;
        a     = ((j >> hl) << (hl + 4'd1)) | (j & mask);
        b     = a | h;
        tm    = (j & mask) << st;
        pa    = ^a;
        ia    = a[LOGN-1:1];
        ib    = b[LOGN-1:1];
    end
    logic [LOGN-1:0] twm;
    logic [TW-1:0]   wr0, wi0;
    assign twm = tm;
    fft_twiddle_quarter #(.LOGC(LOGN), .TW(TW), .STAGES(TWSTAGES)) u_tw (.clk(clk), .m(twm), .wr(wr0), .wi(wi0));
    logic [TW-1:0]   wr2, wi2;
    logic [TW-1:0]   wr1, wi1;
    always_ff @(posedge clk) begin
        wr1 <= wr0;
        wi1 <= wi0;
    end
    always_comb begin
        wr2 = (TWSTAGES == 1) ? wr1 : wr0;
        wi2 = (TWSTAGES == 1) ? wi1 : wi0;
    end

    // control pipeline t0 .. t0 + LP
    logic            en_p [LP+1];
    logic            pa_p [LP+1];
    logic [LOGN-2:0] ia_p [LP+1];
    logic [LOGN-2:0] ib_p [LP+1];
    always_comb begin
        en_p[0] = issue;
        pa_p[0] = pa;
        ia_p[0] = ia;
        ib_p[0] = ib;
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            for (int k = 1; k <= LP; k++) en_p[k] <= 1'b0;
        end else begin
            for (int k = 1; k <= LP; k++) en_p[k] <= en_p[k-1];
        end
        for (int k = 1; k <= LP; k++) begin
            pa_p[k] <= pa_p[k-1];
            ia_p[k] <= ia_p[k-1];
            ib_p[k] <= ib_p[k-1];
        end
    end

    // read ports: the butterfly's two words, or the word being unloaded (both banks get the same in-bank address)
    logic [LOGN-1:0] ua;
    logic            ua_par;
    fft_bitrev #(.LOGN(LOGN)) u_rev (.a(oc), .y(ua));
    always_comb begin
        ra0 = pa ? ib : ia;
        ra1 = pa ? ia : ib;
        if (state == S_UNLD) begin
            ra0 = (ORDER == 0) ? ua[LOGN-1:1] : oc[LOGN-1:1];
            ra1 = ra0;
        end
        ua_par = (ORDER == 0) ? ^ua : ^oc;
    end

    // ---- t1: add and subtract ---------------------------------------------------------------------------------------------------------
    logic signed [WM-1:0] a_r, a_i, b_r, b_i;
    // verilator lint_off UNUSEDSIGNAL
    logic signed [WM:0]   s_r, s_i, d_r, d_i;
    // verilator lint_on UNUSEDSIGNAL
    logic signed [WM-1:0] ts_r, ts_i, td_r, td_i;
    always_comb begin
        {a_r, a_i} = pa_p[1] ? rd1 : rd0;
        {b_r, b_i} = pa_p[1] ? rd0 : rd1;
        s_r = (WM + 1)'(a_r) + (WM + 1)'(b_r);
        s_i = (WM + 1)'(a_i) + (WM + 1)'(b_i);
        d_r = (WM + 1)'(a_r) - (WM + 1)'(b_r);
        d_i = (WM + 1)'(a_i) - (WM + 1)'(b_i);
        ts_r = WM'((SCALE != 0) ? ((s_r + (WM + 1)'(RND)) >>> 1) : s_r);
        ts_i = WM'((SCALE != 0) ? ((s_i + (WM + 1)'(RND)) >>> 1) : s_i);
        td_r = WM'((SCALE != 0) ? ((d_r + (WM + 1)'(RND)) >>> 1) : d_r);
        td_i = WM'((SCALE != 0) ? ((d_i + (WM + 1)'(RND)) >>> 1) : d_i);
    end
    logic [WM-1:0] sd_r [MULSTAGES+2];
    logic [WM-1:0] sd_i [MULSTAGES+2];
    logic [WM-1:0] dd_r, dd_i;
    always_ff @(posedge clk) begin
        sd_r[0] <= ts_r;
        sd_i[0] <= ts_i;
        for (int k = 1; k < MULSTAGES + 2; k++) begin
            sd_r[k] <= sd_r[k-1];
            sd_i[k] <= sd_i[k-1];
        end
        dd_r <= td_r;
        dd_i <= td_i;
    end

    // ---- t2: twiddle multiply, rounded --------------------------------------------------------------------------------------------------
    logic [WP-1:0] pr, pi;
    generate
        if (CMUL == 3) begin : g_m3
            fft_cmul_m3 #(.WA(WM), .WB(TW), .STAGES(MULSTAGES)) u_m (.clk(clk), .ar(dd_r), .ai(dd_i), .br(wr2), .bi(wi2), .pr(pr), .pi(pi));
        end else begin : g_m4
            fft_cmul_m4 #(.WA(WM), .WB(TW), .STAGES(MULSTAGES)) u_m (.clk(clk), .ar(dd_r), .ai(dd_i), .br(wr2), .bi(wi2), .pr(pr), .pi(pi));
        end
    endgenerate
    // verilator lint_off UNUSEDSIGNAL
    logic signed [WP-1:0] sr, si, rr, ri;
    // verilator lint_on UNUSEDSIGNAL
    logic [WM-1:0] pr_q, pi_q;
    always_comb begin
        sr = pr;
        si = pi;
        rr = (RND != 0) ? (sr + (WP)'(1 << (TW - 3))) >>> (TW - 2) : sr >>> (TW - 2);
        ri = (RND != 0) ? (si + (WP)'(1 << (TW - 3))) >>> (TW - 2) : si >>> (TW - 2);
    end
    always_ff @(posedge clk) begin
        pr_q <= WM'(rr);
        pi_q <= WM'(ri);
    end

    // ---- write back (clock t0 + LP) ---------------------------------------------------------------------------------------------------
    logic [2*WM-1:0] sw, pw;
    logic            ld_bank0;
    always_comb begin
        sw = {sd_r[MULSTAGES+1], sd_i[MULSTAGES+1]};
        pw = {pr_q, pi_q};
        ld_bank0 = ~ld_par;
        we0 = ld_we ? ld_bank0 : en_p[LP];
        we1 = ld_we ? ~ld_bank0 : en_p[LP];
        wa0 = ld_we ? ld_pos[LOGN-1:1] : (pa_p[LP] ? ib_p[LP] : ia_p[LP]);
        wa1 = ld_we ? ld_pos[LOGN-1:1] : (pa_p[LP] ? ia_p[LP] : ib_p[LP]);
        wd0 = ld_we ? ld_d : (pa_p[LP] ? pw : sw);
        wd1 = ld_we ? ld_d : (pa_p[LP] ? sw : pw);
    end

    // ---- control ----------------------------------------------------------------------------------------------------------------------
    always_ff @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            lc <= '0; oc <= '0; st <= '0; cyc <= '0; inv_f <= 1'b0; ov <= 1'b0; os_q <= 1'b0; ob <= 1'b0;
        end else begin
            if (adv) begin
                ov   <= (state == S_UNLD);
                os_q <= (state == S_UNLD) && (oc == '0);
                ob   <= ua_par;
            end
            case (state)
                S_IDLE: begin
                    if (in_valid && in_sof) begin
                        inv_f <= in_inverse;
                        lc    <= LOGN'(1);
                        state <= S_LOAD;
                    end
                end
                S_LOAD: begin
                    if (in_valid) begin
                        lc <= lc + 1'b1;
                        if (lc == LOGN'(N - 1)) begin
                            state <= S_COMP;
                            st    <= '0;
                            cyc   <= '0;
                        end
                    end
                end
                S_COMP: begin
                    if (cyc == CW'(N / 2 + LP - 1)) begin
                        cyc <= '0;
                        if (st == 4'(LOGN - 1)) begin
                            state <= S_UNLD;
                            oc    <= '0;
                        end else begin
                            st <= st + 1'b1;
                        end
                    end else begin
                        cyc <= cyc + 1'b1;
                    end
                end
                default: begin
                    if (adv) begin
                        oc <= oc + 1'b1;
                        if (oc == LOGN'(N - 1)) state <= S_IDLE;
                    end
                end
            endcase
        end
    end

    // ---- output: the word read in the previous clock, direction swap ----------------------------------------------------------------------
    logic [2*WM-1:0] od;
    always_comb begin
        od        = ob ? rd1 : rd0;
        out_valid = ov;
        out_sof   = os_q;
        out_re    = inv_f ? od[WM-1:0] : od[2*WM-1:WM];
        out_im    = inv_f ? od[2*WM-1:WM] : od[WM-1:0];
    end
endmodule
