// adder_carry_select: integer adder/subtractor, carry-select blocks of BLOCK bits (arith brief 139a, variant "carry_select").
//
// Function: as adder_ripple (arith/adder/spec.md). Latency 0 clocks (combinational; clk unused, kept for a common port list).
// Block 0 is a ripple adder with the real carry in. Every higher block is computed twice, with carry in 0 and with carry in 1; the carry out of
// the block below selects the result, and the carries are selected block to block. The last block may be narrower than BLOCK.
//
// Intended primitive use (stated before any Vivado run; not yet measured): 1 + 2 * (NB - 1) carry chains of at most BLOCK bits (CARRY4 or
// CARRY8 cells in each), LUT multiplexers (2:1 per sum bit, one per block carry). About twice the adder LUTs of the ripple variant. On a
// fabric whose carry chain is a hard macro the ripple variant is expected to be as fast or faster up to a few tens of bits, so this variant is
// the "does the textbook trade-off hold here" comparison point, not an expected winner.
module adder_carry_select #(
    parameter int WIDTH = 32,
    parameter int BLOCK = 8
) (
    // verilator lint_off UNUSEDSIGNAL
    input  logic             clk,
    // verilator lint_on UNUSEDSIGNAL
    input  logic [WIDTH-1:0] a,
    input  logic [WIDTH-1:0] b,
    input  logic             cin,
    input  logic             sub,
    output logic [WIDTH-1:0] s,
    output logic             co,
    output logic             ovf
);
    localparam int NB = (WIDTH + BLOCK - 1) / BLOCK;

    logic [WIDTH-1:0] be;
    logic             ce;
    logic [NB:0]      c;                  // c[i] = carry into block i; c[NB] is the carry out
    assign be   = b ^ {WIDTH{sub}};
    assign ce   = cin ^ sub;
    assign c[0] = ce;
    assign co   = c[NB];

    for (genvar i = 0; i < NB; i++) begin : g_blk
        localparam int LO = i * BLOCK;
        localparam int BW = (LO + BLOCK <= WIDTH) ? BLOCK : WIDTH - LO;
        if (i == 0) begin : g_first
            assign {c[1], s[LO +: BW]} = {1'b0, a[LO +: BW]} + {1'b0, be[LO +: BW]} + {{BW{1'b0}}, c[0]};
        end else begin : g_sel
            logic [BW-1:0] s0, s1;        // block sum for carry in 0 and 1
            logic          c0, c1;
            assign {c0, s0} = {1'b0, a[LO +: BW]} + {1'b0, be[LO +: BW]};
            assign {c1, s1} = {1'b0, a[LO +: BW]} + {1'b0, be[LO +: BW]} + {{BW{1'b0}}, 1'b1};
            assign s[LO +: BW] = c[i] ? s1 : s0;
            assign c[i+1]      = c[i] ? c1 : c0;
        end
    end

    assign ovf = (a[WIDTH-1] == be[WIDTH-1]) && (s[WIDTH-1] != a[WIDTH-1]);
endmodule
