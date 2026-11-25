// mac_dsp_cascade: multiply-accumulate with the lanes chained as a DSP cascade (arith brief 139a, variant "dsp_cascade").
//
// Function: as mac_dsp (arith/mac/spec.md): on a clock with en = 1, acc <= (clr ? 0 : acc) + sum over the LANES lanes of a_k * b_k, modulo 2**ACCW.
// Structure: lane k computes q_k <= a_k * b_k + q_(k-1) (q_(-1) = 0) in its own register, the way a DSP48's P output feeds the next DSP's PCIN; lane k's
// operands are delayed by k clocks so that the partial sum and the product that join belong to the same sample. The last lane's sum is then
// accumulated into acc. Latency LANES + 1 clocks, one sample per clock; en and clr travel with the data (LANES registers) and rst (synchronous)
// clears acc and the en pipeline, discarding every sample presented before or on the clock where it is high. With LANES = 1 it is a 2-clock MAC.
//
// Intended primitive use (stated before any Vivado run; not yet measured): LANES DSP48 blocks joined PCOUT to PCIN (no fabric adder between the
// lanes: that is the point of this variant against mac_dsp, whose lane sum is a fabric adder), plus the operand skew registers (about
// (WA + WB) * LANES * (LANES - 1) / 2 flip-flops, or SRL16/SRL32 if Vivado maps the delay lines to shift registers) and a final accumulate in the
// fabric or in one more DSP through its C port (left to Vivado).
module mac_dsp_cascade #(
    parameter int WA     = 16,
    parameter int WB     = 16,
    parameter int LANES  = 2,
    parameter int ACCW   = 40,
    parameter int SIGNED = 1
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

    for (genvar k = 0; k < LANES; k++) begin : g_lane
        logic [WA-1:0] a_d;                      // lane k's operands, k clocks late
        logic [WB-1:0] b_d;
        if (k == 0) begin : g_nodelay
            assign a_d = a[0 +: WA];
            assign b_d = b[0 +: WB];
        end else begin : g_delay
            logic [WA-1:0] sra [k];
            logic [WB-1:0] srb [k];
            always_ff @(posedge clk) begin
                sra[0] <= a[k*WA +: WA];
                srb[0] <= b[k*WB +: WB];
                for (int j = 1; j < k; j++) begin
                    sra[j] <= sra[j-1];
                    srb[j] <= srb[j-1];
                end
            end
            assign a_d = sra[k-1];
            assign b_d = srb[k-1];
        end
        logic signed [WA:0] ea;
        logic signed [WB:0] eb;
        // verilator lint_off UNUSEDSIGNAL
        (* use_dsp = "yes" *) logic signed [PW+1:0] full;
        // verilator lint_on UNUSEDSIGNAL
        logic [ACCW-1:0] prod, prev, q;           // this lane's product, the partial sum from lane k-1, this lane's registered sum
        assign ea   = SIGNED != 0 ? {a_d[WA-1], a_d} : {1'b0, a_d};
        assign eb   = SIGNED != 0 ? {b_d[WB-1], b_d} : {1'b0, b_d};
        assign full = ea * eb;
        // verilator lint_off WIDTHTRUNC
        assign prod = ACCW'(SIGNED != 0 ? $signed(full[PW-1:0]) : $signed({1'b0, full[PW-1:0]}));
        // verilator lint_on WIDTHTRUNC
        if (k == 0) begin : g_first
            assign prev = '0;
        end else begin : g_chain
            assign prev = g_lane[k-1].q;
        end
        always_ff @(posedge clk) q <= prod + prev;
    end

    // en and clr, LANES clocks late: the last lane's q is for the sample presented LANES - 1 clocks ago
    logic [LANES-1:0] en_sr, clr_sr;
    always_ff @(posedge clk) begin
        clr_sr[0] <= clr;
        for (int j = 1; j < LANES; j++) clr_sr[j] <= clr_sr[j-1];
        if (rst) begin
            en_sr <= '0;
        end else begin
            en_sr[0] <= en;
            for (int j = 1; j < LANES; j++) en_sr[j] <= en_sr[j-1];
        end
    end

    always_ff @(posedge clk) begin
        if (rst)                  acc <= '0;
        else if (en_sr[LANES-1])  acc <= (clr_sr[LANES-1] ? '0 : acc) + g_lane[LANES-1].q;
    end
endmodule
