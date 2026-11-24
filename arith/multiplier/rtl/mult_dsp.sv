// mult_dsp: WA x WB multiplier written for the DSP blocks (arith brief 139a, variant "dsp").
//
// Function (arith/multiplier/spec.md): p = a * b, full width WA + WB bits, both operands signed (SIGNED = 1) or both unsigned (SIGNED = 0).
// Latency STAGES clocks (0 to 3), one product per clock. The registers are placed where DSP48 has them: STAGES 1 = the product register (PREG);
// 2 = the multiplier-output register (MREG) and PREG; 3 = the operand registers (AREG, BREG) as well. No reset: the pipeline holds data only.
//
// Intended primitive use (stated before any Vivado run; not yet measured): the `*` is mapped to DSP48E1 (7 series, 25 x 18 signed) or DSP48E2
// (UltraScale+, 27 x 18 signed) blocks, tiled by Vivado when an operand is wider (about ceil((WA+1)/25) * ceil((WB+1)/18) blocks on 7 series;
// an unsigned operand costs one extra bit because the DSP multiplier is signed). With STAGES = 3 the registers are absorbed (no fabric FF); with
// fewer they may stay in the fabric. The use_dsp attribute asks for the DSP explicitly (Vivado would otherwise choose LUTs for a small product).
module mult_dsp #(
    parameter int WA     = 18,
    parameter int WB     = 18,
    parameter int SIGNED = 1,
    parameter int STAGES = 3
) (
    // verilator lint_off UNUSEDSIGNAL
    input  logic                clk,
    // verilator lint_on UNUSEDSIGNAL
    input  logic [WA-1:0]       a,
    input  logic [WB-1:0]       b,
    output logic [WA+WB-1:0]    p
);
    logic [WA-1:0]    a_s;      // operands as the multiplier sees them (registered when STAGES = 3)
    logic [WB-1:0]    b_s;
    if (STAGES >= 3) begin : g_in
        logic [WA-1:0] a_r;
        logic [WB-1:0] b_r;
        always_ff @(posedge clk) begin
            a_r <= a;
            b_r <= b;
        end
        assign a_s = a_r;
        assign b_s = b_r;
    end else begin : g_noin
        assign a_s = a;
        assign b_s = b;
    end

    logic signed [WA:0] ea;     // one extra bit so that an unsigned operand is a non-negative signed one
    logic signed [WB:0] eb;
    assign ea = SIGNED != 0 ? {a_s[WA-1], a_s} : {1'b0, a_s};
    assign eb = SIGNED != 0 ? {b_s[WB-1], b_s} : {1'b0, b_s};
    // verilator lint_off UNUSEDSIGNAL
    (* use_dsp = "yes" *) logic signed [WA+WB+1:0] full;
    // verilator lint_on UNUSEDSIGNAL
    assign full = ea * eb;      // both operands signed, so both are sign-extended to the width of full before the multiply

    logic [WA+WB-1:0] m_s;      // multiplier output as the next stage sees it
    if (STAGES >= 2) begin : g_m
        logic [WA+WB-1:0] m_r;
        always_ff @(posedge clk) m_r <= full[WA+WB-1:0];
        assign m_s = m_r;
    end else begin : g_nom
        assign m_s = full[WA+WB-1:0];
    end

    if (STAGES >= 1) begin : g_p
        logic [WA+WB-1:0] p_r;
        always_ff @(posedge clk) p_r <= m_s;
        assign p = p_r;
    end else begin : g_nop
        assign p = m_s;
    end
endmodule
