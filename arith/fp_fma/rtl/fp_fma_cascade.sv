// fp_fma_cascade: multiply-add as a multiplier followed by an adder, TWO roundings (arith brief 139e, variant "cascade").
//
// Function (arith/fp_fma/spec.md): y = round(round(a * b) + c): the product is rounded to the format (round to nearest even), then the sum with c is rounded again. This is NOT the fused
// multiply-add: for some inputs it differs from the exactly rounded a * b + c by one unit in the last place (a double rounding), and where a * b is subnormal or infinite its special cases
// follow the two steps. Latency STAGES_M + STAGES_A: the multiplier's STAGES_M ranks (fp_mul_dsp, 0 to 3) then the adder's STAGES_A ranks (fp_add_single, 0 to 3); c is delayed by
// STAGES_M clocks to meet the product. SUBNORM, round to nearest even, canonical quiet NaN, no flags and no reset are those of the two blocks it is built from.
//
// Intended primitive use (stated before any Vivado run; not yet measured): the sum of its parts and nothing else: the significand product of fp_mul_dsp on DSP blocks (binary32 about 4
// DSP48E1 or 2 DSP48E2), the LUT and carry-chain adder of fp_add_single (about 450 to 600 LUT6 at binary32), the rounding of both, and STAGES_M delay registers of the c word (EXP + MAN + 1
// flip-flops each). No second multiplier; it is smaller than fp_fma_fused (no 3 * SP + 3 bit window and normaliser) and its clock is set by the slower of its two halves.
module fp_fma_cascade #(
    parameter int EXP      = 8,
    parameter int MAN      = 23,
    parameter int SUBNORM  = 1,
    parameter int STAGES_M = 3,
    parameter int STAGES_A = 3
) (
    // verilator lint_off UNUSEDSIGNAL
    input  logic                clk,
    // verilator lint_on UNUSEDSIGNAL
    input  logic [EXP+MAN:0]    a,
    input  logic [EXP+MAN:0]    b,
    input  logic [EXP+MAN:0]    c,
    output logic [EXP+MAN:0]    y
);
    localparam int W = EXP + MAN + 1;
    logic [W-1:0] prod;
    fp_mul_dsp #(.EXP(EXP), .MAN(MAN), .SUBNORM(SUBNORM), .STAGES(STAGES_M)) u_mul (.clk(clk), .a(a), .b(b), .y(prod));

    logic [W-1:0] c_d;                                 // c, delayed to meet the product
    if (STAGES_M == 0) begin : g_nodly
        assign c_d = c;
    end else begin : g_dly
        logic [W-1:0] r [STAGES_M];
        always_ff @(posedge clk) begin
            r[0] <= c;
            for (int i = 1; i < STAGES_M; i++) r[i] <= r[i-1];
        end
        assign c_d = r[STAGES_M-1];
    end
    fp_add_single #(.EXP(EXP), .MAN(MAN), .SUBNORM(SUBNORM), .STAGES(STAGES_A)) u_add (.clk(clk), .a(prod), .b(c_d), .y(y));
endmodule
