// mult_booth_r4: WA x WB radix-4 Booth multiplier built from LUTs and carry chains, no DSP (arith brief 139a, variant "booth_r4").
//
// Function: as mult_dsp (arith/multiplier/spec.md). Latency REG clocks (0 or 1): an optional output register. No reset.
// b is recoded into NP = ceil((WB + 1 - SIGNED) / 2) digits d_i in {-2, -1, 0, 1, 2} (d_i = -2 b[2i+1] + b[2i] + b[2i-1]); the product is the
// sum of d_i * a * 4**i. About half as many rows as the plain array (mult_lut_array), at the price of a selector per partial-product bit.
// An unsigned b is zero-extended by one bit first, so that its top digit is non-negative.
//
// Intended primitive use (stated before any Vivado run; not yet measured): 0 DSP (use_dsp = "no"); about NP - 1 carry chains of up to WA + WB
// bits, so roughly half the adder rows (and half the series carry delay) of lut_array, with the select-and-negate logic (about one LUT per
// partial-product bit, the negate's +1 folded into the carry chain) in front of each. Whether it is smaller or faster than lut_array on a
// fabric whose adders are hard carry chains is what the Vivado runs will measure.
module mult_booth_r4 #(
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
    localparam int PW  = WA + WB;
    localparam int WBX = WB + (SIGNED != 0 ? 0 : 1);
    localparam int NP  = (WBX + 1) / 2;

    logic [PW-1:0] ea, ea2;
    assign ea  = SIGNED != 0 ? {{WB{a[WA-1]}}, a} : {{WB{1'b0}}, a};
    assign ea2 = ea << 1;

    // b extended to 2*NP bits, then a 0 appended below: digit i reads bits [2i+2:2i] of bxe
    // verilator lint_off UNUSEDSIGNAL
    logic [2*NP+WB-1:0] bwide;
    // verilator lint_on UNUSEDSIGNAL
    logic [2*NP:0]      bxe;
    assign bwide = {{(2 * NP){SIGNED != 0 ? b[WB-1] : 1'b0}}, b};
    assign bxe   = {bwide[2*NP-1:0], 1'b0};

    (* use_dsp = "no" *) logic [PW-1:0] acc;
    always_comb begin
        acc = '0;
        for (int i = 0; i < NP; i++) begin
            case (bxe[2*i +: 3])
                3'b001, 3'b010: acc = acc + (ea << (2 * i));        // +a
                3'b011:         acc = acc + (ea2 << (2 * i));       // +2a
                3'b100:         acc = acc - (ea2 << (2 * i));       // -2a
                3'b101, 3'b110: acc = acc - (ea << (2 * i));        // -a
                default:        acc = acc;                          // 000, 111: 0
            endcase
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
