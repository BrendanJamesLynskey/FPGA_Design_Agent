// fft_cmul_m4: complex multiplier, four real multipliers (arith brief 148, variant "m4").
//
// Function (arith/fft_cmul/spec.md): p = a * b for a = ar + j ai (WA-bit signed parts) and b = br + j bi (WB-bit signed parts), EXACT:
// pr = ar*br - ai*bi and pi = ar*bi + ai*br, each WA+WB+1 bits signed, no rounding, no overflow possible. STAGES register ranks (0 to 3, latency STAGES):
// rank 1 is after the output, rank 2 also before the multipliers (operand registers), rank 3 also after the four products (product registers). No reset: data only.
//
// Intended primitive use (stated before any Vivado run; not yet measured): four WA x WB signed multipliers and two adders. DSP48E1 (7 series, 25 x 18) or DSP48E2
// (UltraScale+, 27 x 18): four DSP blocks for operands up to 25 x 18 (27 x 18), the adders in the DSP post-adder when STAGES is 3 (pr = ar*br - ai*bi is one DSP
// cascade pair). Few LUTs and no BRAM. The multiplier is inferred with `*`, the use_dsp attribute asks for DSP.
module fft_cmul_m4 #(
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
    logic signed [WA-1:0] ar1, ai1;
    logic signed [WB-1:0] br1, bi1;
    always_comb begin
        ar1 = ar; ai1 = ai; br1 = br; bi1 = bi;
    end
    logic signed [WA-1:0] ar2, ai2;
    logic signed [WB-1:0] br2, bi2;
    always_ff @(posedge clk) begin
        ar2 <= ar1; ai2 <= ai1; br2 <= br1; bi2 <= bi1;
    end
    logic signed [WA-1:0] xa, xb;
    logic signed [WB-1:0] ya, yb;
    always_comb begin
        xa = (STAGES >= 2) ? ar2 : ar1;
        xb = (STAGES >= 2) ? ai2 : ai1;
        ya = (STAGES >= 2) ? br2 : br1;
        yb = (STAGES >= 2) ? bi2 : bi1;
    end
    (* use_dsp = "yes" *) logic signed [WA+WB-1:0] m_rr, m_ii, m_ri, m_ir;
    always_comb begin
        m_rr = xa * ya;
        m_ii = xb * yb;
        m_ri = xa * yb;
        m_ir = xb * ya;
    end
    logic signed [WA+WB-1:0] q_rr, q_ii, q_ri, q_ir;
    always_ff @(posedge clk) begin
        q_rr <= m_rr; q_ii <= m_ii; q_ri <= m_ri; q_ir <= m_ir;
    end
    logic signed [WA+WB-1:0] s_rr, s_ii, s_ri, s_ir;
    always_comb begin
        s_rr = (STAGES >= 3) ? q_rr : m_rr;
        s_ii = (STAGES >= 3) ? q_ii : m_ii;
        s_ri = (STAGES >= 3) ? q_ri : m_ri;
        s_ir = (STAGES >= 3) ? q_ir : m_ir;
    end
    logic signed [WP-1:0] sum_r, sum_i;
    always_comb begin
        sum_r = WP'(s_rr) - WP'(s_ii);
        sum_i = WP'(s_ri) + WP'(s_ir);
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
