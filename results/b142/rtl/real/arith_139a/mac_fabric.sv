// mac_fabric: multiply-accumulate built from LUTs and carry chains, no DSP (arith brief 139a, variant "fabric").
//
// Function: as mac_dsp (arith/mac/spec.md): on a clock with en = 1, acc <= (clr ? 0 : acc) + sum over the LANES lanes of a_k * b_k, modulo 2**ACCW.
// Every lane's product is the sum of WB shifted copies of a_k gated by the bits of b_k (the sign row subtracted when signed), added straight into
// the lane sum, which an ACCW-bit adder then adds to acc. Latency NREG clocks (1 or 2): 1 = acc only; 2 = the lane sum is registered (with en and
// clr) before the accumulate. rst (synchronous) clears acc and the en register, discarding every sample presented before or on the clock where it
// is high.
//
// Intended primitive use (stated before any Vivado run; not yet measured): 0 DSP (use_dsp = "no"); LANES * (WB) adders of up to ACCW bits in series
// (CARRY4/CARRY8 chains) and about LANES * WA * WB LUTs, plus the ACCW-bit accumulate chain and ACCW flip-flops (and ACCW more with NREG = 2). The
// slowest and largest variant by design: it is the answer to "what does the MAC cost if the DSPs are all used elsewhere".
module mac_fabric #(
    parameter int WA     = 16,
    parameter int WB     = 16,
    parameter int LANES  = 1,
    parameter int ACCW   = 40,
    parameter int SIGNED = 1,
    parameter int NREG   = 1
) (
    input  logic                  clk,
    input  logic                  rst,
    input  logic                  en,
    input  logic                  clr,
    input  logic [LANES*WA-1:0]   a,
    input  logic [LANES*WB-1:0]   b,
    output logic [ACCW-1:0]       acc
);
    (* use_dsp = "no" *) logic [ACCW-1:0] sum;
    always_comb begin
        sum = '0;
        for (int k = 0; k < LANES; k++) begin
            for (int i = 0; i < WB; i++) begin
                // verilator lint_off WIDTHTRUNC
                if (SIGNED != 0 && i == WB - 1) sum = sum - (b[k*WB+i] ? ((ACCW'($signed(a[k*WA +: WA]))) << i) : '0);   // the sign bit of b has weight -2**(WB-1)
                else if (SIGNED != 0)           sum = sum + (b[k*WB+i] ? ((ACCW'($signed(a[k*WA +: WA]))) << i) : '0);
                else                            sum = sum + (b[k*WB+i] ? ((ACCW'(a[k*WA +: WA])) << i) : '0);
                // verilator lint_on WIDTHTRUNC
            end
        end
    end

    logic [ACCW-1:0] sum_s;
    logic            en_s, clr_s;
    if (NREG >= 2) begin : g_reg
        logic [ACCW-1:0] sum_r;
        logic            en_r, clr_r;
        always_ff @(posedge clk) begin
            sum_r <= sum;
            clr_r <= clr;
            if (rst) en_r <= 1'b0;
            else     en_r <= en;
        end
        assign sum_s = sum_r;
        assign en_s  = en_r;
        assign clr_s = clr_r;
    end else begin : g_noreg
        assign sum_s = sum;
        assign en_s  = en;
        assign clr_s = clr;
    end

    always_ff @(posedge clk) begin
        if (rst)       acc <= '0;
        else if (en_s) acc <= (clr_s ? '0 : acc) + sum_s;
    end
endmodule
