// dsp_mul_pipe (brief 185): one A x B multiply with the registers placed in the RTL, to measure which of them Vivado packs into the DSP slice.
//
// Function: p = a * b (full width WA + WB, both operands signed). Latency NA + NM + NP clocks from the operand inputs to p, one product per clock.
// Registers (all without reset unless RSTP): NA operand registers on a and on b (0, 1 or 2 deep = AREG/BREG 0, 1, 2), NM registers after the multiply
// (MREG, 0 or 1), NP registers on the output (PREG, 0 or 1). RSTP 0 = no reset on the P register, 1 = synchronous reset (rst), 2 = asynchronous reset.
// Intended primitive use (stated before the run): one DSP48E1 (7 series) or DSP48E2 (UltraScale+), all NA + NM + NP registers inside it.
module dsp_mul_pipe #(
    parameter int WA   = 18,
    parameter int WB   = 18,
    parameter int NA   = 1,
    parameter int NM   = 1,
    parameter int NP   = 1,
    parameter int RSTP = 0
) (
    input  logic                    clk,
    input  logic                    rst,
    input  logic signed [WA-1:0]    a,
    input  logic signed [WB-1:0]    b,
    output logic signed [WA+WB-1:0] p
);
    logic signed [WA-1:0] a_s;
    logic signed [WB-1:0] b_s;
    if (NA == 0) begin : g_a0
        assign a_s = a;
        assign b_s = b;
    end else begin : g_a
        logic signed [WA-1:0] a_r [NA];
        logic signed [WB-1:0] b_r [NA];
        always_ff @(posedge clk) begin
            a_r[0] <= a;
            b_r[0] <= b;
            for (int i = 1; i < NA; i++) begin
                a_r[i] <= a_r[i-1];
                b_r[i] <= b_r[i-1];
            end
        end
        assign a_s = a_r[NA-1];
        assign b_s = b_r[NA-1];
    end

    logic signed [WA+WB-1:0] full, m_s;
    assign full = a_s * b_s;
    if (NM != 0) begin : g_m
        logic signed [WA+WB-1:0] m_r;
        always_ff @(posedge clk) m_r <= full;
        assign m_s = m_r;
    end else begin : g_nm
        assign m_s = full;
    end

    if (NP == 0) begin : g_np0
        assign p = m_s;
    end else if (RSTP == 2) begin : g_pa
        always_ff @(posedge clk or posedge rst) if (rst) p <= '0; else p <= m_s;
    end else if (RSTP == 1) begin : g_ps
        always_ff @(posedge clk) if (rst) p <= '0; else p <= m_s;
    end else begin : g_p
        always_ff @(posedge clk) p <= m_s;
    end
endmodule
