// adder_ripple: integer adder/subtractor on one carry chain (arith brief 139a, variant "ripple").
//
// Function (arith/adder/spec.md): sub = 0: s = a + b + cin; sub = 1: s = a - b - cin (cin is the borrow in); both modulo 2**WIDTH.
// co is the carry out of the underlying adder (so co = 1 means "no borrow" when sub = 1); ovf is signed (two's complement) overflow.
// Latency 0 clocks: combinational. clk is unused and kept so that every variant has the same ports.
//
// Intended primitive use (stated before any Vivado run; not yet measured): the single `+` is one carry chain, CARRY4 cells on 7 series
// (ceil(WIDTH/4) of them) or CARRY8 cells on UltraScale+ (ceil(WIDTH/8)), with about one LUT per bit for the operand XOR (b ^ sub) and the
// propagate term. No DSP, no flip-flop. Delay grows linearly in WIDTH but at the carry chain's few tens of picoseconds per 4 or 8 bits.
module adder_ripple #(
    parameter int WIDTH = 32
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
    logic [WIDTH-1:0] be;      // b, inverted when subtracting: a - b - cin = a + ~b + ~cin (mod 2**WIDTH, and the carry out is the same)
    logic             ce;
    assign be = b ^ {WIDTH{sub}};
    assign ce = cin ^ sub;
    assign {co, s} = {1'b0, a} + {1'b0, be} + {{WIDTH{1'b0}}, ce};
    assign ovf = (a[WIDTH-1] == be[WIDTH-1]) && (s[WIDTH-1] != a[WIDTH-1]);
endmodule
