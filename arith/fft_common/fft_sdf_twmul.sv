// fft_sdf_twmul: the twiddle-factor multiplier between two radix-2^2 pairs of fft_sdf_r22 (arith brief 148).
//
// The word on (xr, xi) is the output of a pair's second stage, and pos (registered with it) is its position in the frame. Within a block of M = 2**LM words the twiddle exponent is
// k * i with i = pos mod (M/4) and k = 2 * g[0] + g[1], g = the quarter of the block (pos / (M/4)); the twiddle is exp(-j 2 pi k i / M), read from fft_twiddle_quarter, TWSTAGES clocks
// after the address. The word is delayed to match, multiplied (CMUL = 4 or 3 real multipliers, MULSTAGES ranks), and the exact product is shifted right by TW-2 with the rounding
// RND says and truncated to the word width. The result is registered. Latency from (xr, xi, pos) to (yr, yi): TWSTAGES + MULSTAGES + 1.
//
// Intended primitive use (not yet measured): 3 or 4 DSP blocks (CMUL), the twiddle ROM and about 3 * (W + TW) LUTs of rounding and address arithmetic.
module fft_sdf_twmul #(
    parameter int LOGN      = 6,
    parameter int LM        = 6,
    parameter int W         = 16,
    parameter int TW        = 16,
    parameter int RND       = 1,
    parameter int CMUL      = 4,
    parameter int TWSTAGES  = 1,
    parameter int MULSTAGES = 2
) (
    input  logic                clk,
    // verilator lint_off UNUSEDSIGNAL
    input  logic [LOGN-1:0]     pos,      // only the low LM bits are used
    // verilator lint_on UNUSEDSIGNAL
    input  logic [W-1:0]        xr,
    input  logic [W-1:0]        xi,
    output logic [W-1:0]        yr,
    output logic [W-1:0]        yi
);
    localparam int WP = W + TW + 1;
    logic [LM-1:0] pm, e;
    logic [LM-3:0] i;
    logic [1:0]    g, k;
    always_comb begin
        pm = pos[LM-1:0];
        i  = pm[LM-3:0];
        g  = pm[LM-1:LM-2];
        k  = {g[0], g[1]};
        case (k)
            2'd0:    e = '0;
            2'd1:    e = LM'(i);
            2'd2:    e = LM'(i) << 1;
            default: e = LM'(i) + (LM'(i) << 1);
        endcase
    end
    logic [TW-1:0] wr, wi;
    fft_twiddle_quarter #(.LOGC(LM), .TW(TW), .STAGES(TWSTAGES)) u_tw (.clk(clk), .m(e), .wr(wr), .wi(wi));
    logic [W-1:0] dr [TWSTAGES];                 // the data delayed to meet the twiddle: registers only, word k is k + 1 clocks old
    logic [W-1:0] di [TWSTAGES];
    always_ff @(posedge clk) begin
        dr[0] <= xr;
        di[0] <= xi;
        for (int s = 1; s < TWSTAGES; s++) begin
            dr[s] <= dr[s-1];
            di[s] <= di[s-1];
        end
    end
    logic [WP-1:0] pr, pi;
    generate
        if (CMUL == 3) begin : g_m3
            fft_cmul_m3 #(.WA(W), .WB(TW), .STAGES(MULSTAGES)) u_m (.clk(clk), .ar(dr[TWSTAGES-1]), .ai(di[TWSTAGES-1]), .br(wr), .bi(wi), .pr(pr), .pi(pi));
        end else begin : g_m4
            fft_cmul_m4 #(.WA(W), .WB(TW), .STAGES(MULSTAGES)) u_m (.clk(clk), .ar(dr[TWSTAGES-1]), .ai(di[TWSTAGES-1]), .br(wr), .bi(wi), .pr(pr), .pi(pi));
        end
    endgenerate
    // verilator lint_off UNUSEDSIGNAL
    logic signed [WP-1:0] sr, si, rr, ri;      // the product is wider than the word: only the low W bits of the shifted result are kept
    // verilator lint_on UNUSEDSIGNAL
    always_comb begin
        sr = pr;
        si = pi;
        rr = (RND != 0) ? (sr + (WP)'(1 << (TW - 3))) >>> (TW - 2) : sr >>> (TW - 2);
        ri = (RND != 0) ? (si + (WP)'(1 << (TW - 3))) >>> (TW - 2) : si >>> (TW - 2);
    end
    always_ff @(posedge clk) begin
        yr <= W'(rr);
        yi <= W'(ri);
    end
endmodule
