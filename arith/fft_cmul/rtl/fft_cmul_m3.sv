// fft_cmul_m3: complex multiplier, three real multipliers (arith brief 148, variant "m3").
//
// Function (arith/fft_cmul/spec.md): the same exact product as fft_cmul_m4, pr = ar*br - ai*bi and pi = ar*bi + ai*br, each WA+WB+1 bits signed, by the three-multiplication
// identity k1 = br * (ar + ai), pr = k1 - ai * (br + bi), pi = k1 + ar * (bi - br). It trades one multiplier for three pre-adders and three post-adders; every sum is
// held in full width, so the result equals the four-multiplier form bit for bit. STAGES register ranks (0 to 3): rank 1 after the output, rank 2 also before the multipliers
// (after the pre-adders), rank 3 also after the three products. No reset: data only.
//
// Intended primitive use (stated before any Vivado run; not yet measured): three signed multipliers of (WA+1) x WB, (WB+1) x WA and (WB+1) x WA bits, so 3 DSP blocks
// where the operands fit (the pre-adders widen one operand by one bit, which costs a second DSP when the operand is already 25 (DSP48E1) or 27 (DSP48E2) bits wide); LUTs
// for the three pre-adders and the post-adders (about 4 * (WA + WB) LUTs, carry chains). Pays off in DSP-limited parts.
module fft_cmul_m3 #(
    parameter int WA     = 16,
    parameter int WB     = 16,
    parameter int STAGES = 3
) (
    // verilator lint_off UNUSEDSIGNAL
    input  logic                 clk,
    // verilator lint_on UNUSEDSIGNAL
    input  logic [WA-1:0]        ar,
    input  logic [WA-1:0]        ai,
    input  logic [WB-1:0]        br,
    input  logic [WB-1:0]        bi,
    output logic [WA+WB:0]       pr,
    output logic [WA+WB:0]       pi
);
    localparam int WP = WA + WB + 1;
    logic signed [WA-1:0] sar, sai;
    logic signed [WB-1:0] sbr, sbi;
    logic signed [WA:0]   a_sum;      // ar + ai
    logic signed [WB:0]   b_sum;      // br + bi
    logic signed [WB:0]   b_dif;      // bi - br
    always_comb begin
        sar = ar; sai = ai; sbr = br; sbi = bi;
        a_sum = (WA + 1)'(sar) + (WA + 1)'(sai);
        b_sum = (WB + 1)'(sbr) + (WB + 1)'(sbi);
        b_dif = (WB + 1)'(sbi) - (WB + 1)'(sbr);
    end
    // operand rank: ai, ar, br and the three pre-adder results
    logic signed [WA:0]   a_sum2;
    logic signed [WB:0]   b_sum2, b_dif2;
    logic signed [WA-1:0] ar2, ai2;
    logic signed [WB-1:0] br2;
    always_ff @(posedge clk) begin
        a_sum2 <= a_sum; b_sum2 <= b_sum; b_dif2 <= b_dif; ar2 <= sar; ai2 <= sai; br2 <= sbr;
    end
    logic signed [WA:0]   xs;
    logic signed [WB:0]   ys, yd;
    logic signed [WA-1:0] xr, xi;
    logic signed [WB-1:0] yr;
    always_comb begin
        xs = (STAGES >= 2) ? a_sum2 : a_sum;
        ys = (STAGES >= 2) ? b_sum2 : b_sum;
        yd = (STAGES >= 2) ? b_dif2 : b_dif;
        xr = (STAGES >= 2) ? ar2 : sar;
        xi = (STAGES >= 2) ? ai2 : sai;
        yr = (STAGES >= 2) ? br2 : sbr;
    end
    (* use_dsp = "yes" *) logic signed [WA+WB:0] k1, k2, k3;
    always_comb begin
        k1 = xs * yr;      // br * (ar + ai)
        k2 = xi * ys;      // ai * (br + bi)
        k3 = xr * yd;      // ar * (bi - br)
    end
    logic signed [WA+WB:0] q1, q2, q3;
    always_ff @(posedge clk) begin
        q1 <= k1; q2 <= k2; q3 <= k3;
    end
    logic signed [WP-1:0] sum_r, sum_i;
    always_comb begin
        sum_r = ((STAGES >= 3) ? WP'(q1) : WP'(k1)) - ((STAGES >= 3) ? WP'(q2) : WP'(k2));
        sum_i = ((STAGES >= 3) ? WP'(q1) : WP'(k1)) + ((STAGES >= 3) ? WP'(q3) : WP'(k3));
    end
    logic [WP-1:0] reg_r, reg_i;
    always_ff @(posedge clk) begin
        reg_r <= sum_r;
        reg_i <= sum_i;
    end
    always_comb begin
        pr = (STAGES >= 1) ? reg_r : sum_r;
        pi = (STAGES >= 1) ? reg_i : sum_i;
    end
endmodule
