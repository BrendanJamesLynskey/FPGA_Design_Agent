// mult_lut_array: WA x WB multiplier built from LUTs and carry chains, no DSP (arith brief 139a, variant "lut_array").
//
// Function: as mult_dsp (arith/multiplier/spec.md). Latency REG clocks (0 or 1): an optional output register. No reset.
// The product is the sum of WB shifted copies of a, each gated by one bit of b (the textbook array multiplier); for a signed multiplier the row of
// b's sign bit is subtracted. Every row is added to the running sum by an adder, so there are WB - 1 carry chains in series.
//
// Intended primitive use (stated before any Vivado run; not yet measured): 0 DSP (use_dsp = "no"); about WA * WB / 2 to WA * WB LUTs (the AND of
// each partial-product bit is absorbed in the adder's LUT) and WB - 1 carry chains of up to WA + WB bits (CARRY4 or CARRY8 cells); a long
// combinational path (the rows add in series), so the clock is slow; REG = 1 only registers the result and does not shorten that path.
module mult_lut_array #(
    parameter int WA     = 18,
    parameter int WB     = 18,
    parameter int SIGNED = 1,
    parameter int REG    = 0
) (
    // verilator lint_off UNUSEDSIGNAL
    input  logic                clk,
    // verilator lint_on UNUSEDSIGNAL
    input  logic [WA-1:0]       a,
    input  logic [WB-1:0]       b,
    output logic [WA+WB-1:0]    p
);
    localparam int PW = WA + WB;
    logic [PW-1:0] ea;          // a extended to the product's width: sign-extended when signed, zero-extended otherwise
    assign ea = SIGNED != 0 ? {{WB{a[WA-1]}}, a} : {{WB{1'b0}}, a};

    (* use_dsp = "no" *) logic [PW-1:0] acc;
    always_comb begin
        acc = '0;
        for (int i = 0; i < WB; i++) begin
            if (SIGNED != 0 && i == WB - 1) acc = acc - (b[i] ? (ea << i) : '0);     // the sign bit of b has weight -2**(WB-1)
            else                            acc = acc + (b[i] ? (ea << i) : '0);
        end
    end

    if (REG != 0) begin : g_reg
        logic [PW-1:0] p_r;
        always_ff @(posedge clk) p_r <= acc;
        assign p = p_r;
    end else begin : g_noreg
        assign p = acc;
    end
endmodule
