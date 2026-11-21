// mac_dsp: multiply-accumulate written for the DSP blocks (arith brief 139a, variant "dsp").
//
// Function (arith/mac/spec.md): on a clock with en = 1, acc <= (clr ? 0 : acc) + sum over the LANES lanes of a_k * b_k, modulo 2**ACCW; with en = 0
// acc holds. a_k and b_k are lane k of the packed inputs (a[k*WA +: WA], b[k*WB +: WB]), all signed (SIGNED = 1) or all unsigned. clr starts a new
// sum with this clock's product. rst (synchronous) clears acc and discards every sample presented before or on the clock where it is high.
// Latency NREG clocks (1 to 3), one sample per clock. NREG 1: acc only (the multiplier is combinational in front of it); 2: operand registers
// (AREG, BREG) and acc (PREG); 3: AREG/BREG, the product register (MREG) and PREG.
//
// Intended primitive use (stated before any Vivado run; not yet measured): one DSP48E1 (7 series) or DSP48E2 (UltraScale+) per lane when
// WA <= 25 and WB <= 18 (27 x 18 on UltraScale+), the accumulate in the DSP's own ALU through the P feedback when LANES = 1, and for LANES > 1
// the lane sum feeding the accumulator as a fabric adder tree or a DSP C-port add (left to Vivado). A wider multiplier tiles across several
// DSPs and Vivado uses the PCOUT to PCIN cascade for the partial products. An unsigned operand costs an extra bit (the DSP multiplier is signed).
module mac_dsp #(
    parameter int WA     = 16,
    parameter int WB     = 16,
    parameter int LANES  = 1,
    parameter int ACCW   = 40,
    parameter int SIGNED = 1,
    parameter int NREG   = 3
) (
    input  logic                  clk,
    input  logic                  rst,
    input  logic                  en,
    input  logic                  clr,
    input  logic [LANES*WA-1:0]   a,
    input  logic [LANES*WB-1:0]   b,
    output logic [ACCW-1:0]       acc
);
    localparam int PW = WA + WB;

    // ---- stage 1 (NREG >= 2): operand registers ------------------------------------------------------------
    logic [LANES*WA-1:0] a_s;
    logic [LANES*WB-1:0] b_s;
    logic                en_s, clr_s;
    if (NREG >= 2) begin : g_in
        logic [LANES*WA-1:0] a_r;
        logic [LANES*WB-1:0] b_r;
        logic                en_r, clr_r;
        always_ff @(posedge clk) begin
            a_r   <= a;
            b_r   <= b;
            clr_r <= clr;
            if (rst) en_r <= 1'b0;
            else     en_r <= en;
        end
        assign a_s = a_r;
        assign b_s = b_r;
        assign en_s = en_r;
        assign clr_s = clr_r;
    end else begin : g_noin
        assign a_s = a;
        assign b_s = b;
        assign en_s = en;
        assign clr_s = clr;
    end

    // ---- the lane products ---------------------------------------------------------------------------------
    logic [PW-1:0] pat [LANES];                 // product pattern of each lane, PW bits
    for (genvar k = 0; k < LANES; k++) begin : g_lane
        logic signed [WA:0] ea;                 // one extra bit so an unsigned operand is a non-negative signed one
        logic signed [WB:0] eb;
        // verilator lint_off UNUSEDSIGNAL
        (* use_dsp = "yes" *) logic signed [PW+1:0] full;
        // verilator lint_on UNUSEDSIGNAL
        assign ea   = SIGNED != 0 ? {a_s[k*WA+WA-1], a_s[k*WA +: WA]} : {1'b0, a_s[k*WA +: WA]};
        assign eb   = SIGNED != 0 ? {b_s[k*WB+WB-1], b_s[k*WB +: WB]} : {1'b0, b_s[k*WB +: WB]};
        assign full = ea * eb;
        assign pat[k] = full[PW-1:0];
    end

    // ---- stage 2 (NREG >= 3): product registers ------------------------------------------------------------
    logic [PW-1:0] pat_s [LANES];
    logic          en_m, clr_m;
    if (NREG >= 3) begin : g_m
        logic [PW-1:0] m_r [LANES];
        logic          en_q, clr_q;
        always_ff @(posedge clk) begin
            for (int k = 0; k < LANES; k++) m_r[k] <= pat[k];
            clr_q <= clr_s;
            if (rst) en_q <= 1'b0;
            else     en_q <= en_s;
        end
        always_comb begin
            for (int k = 0; k < LANES; k++) pat_s[k] = m_r[k];
        end
        assign en_m  = en_q;
        assign clr_m = clr_q;
    end else begin : g_nom
        always_comb begin
            for (int k = 0; k < LANES; k++) pat_s[k] = pat[k];
        end
        assign en_m  = en_s;
        assign clr_m = clr_s;
    end

    // ---- the accumulator -----------------------------------------------------------------------------------
    // each pattern extended to ACCW bits (sign-extended when signed), summed, added to acc (or to 0 on clr)
    logic [ACCW-1:0] sum;
    always_comb begin
        sum = '0;
        for (int k = 0; k < LANES; k++) begin
            // verilator lint_off WIDTHTRUNC
            sum = sum + ACCW'(SIGNED != 0 ? $signed(pat_s[k]) : $signed({1'b0, pat_s[k]}));
            // verilator lint_on WIDTHTRUNC
        end
    end
    always_ff @(posedge clk) begin
        if (rst)       acc <= '0;
        else if (en_m) acc <= (clr_m ? '0 : acc) + sum;
    end
endmodule
