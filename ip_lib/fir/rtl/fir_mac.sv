// fir_mac: one multiply-accumulate engine of the folded FIR, written to the standard multiply-accumulate
// inference template so that one DSP slice holds it all: operand registers (A, B) and the product register (M) run
// every clock, the accumulator (P) has a clock enable and zeroes its feedback, not its sum, on the first product.
// No use_dsp attribute: on the whole folded core "yes" pulled the adder tree, counters and comparators into DSP
// slices (21 for 4 engines), and on this module it split each engine into a multiplier slice and an adder slice.
module fir_mac #(
    parameter int DATA_W = 16,
    parameter int COEF_W = 16,
    parameter int ACC_W  = 36
) (
    input  logic                     clk,
    input  logic                     ld_p,       // accumulate
    input  logic                     first,      // with ld_p: start a new sum
    input  logic signed [DATA_W-1:0] a_in,
    input  logic signed [COEF_W-1:0] b_in,
    output logic signed [ACC_W-1:0]  acc
);
    logic signed [DATA_W-1:0]        a;
    logic signed [COEF_W-1:0]        b;
    logic signed [DATA_W+COEF_W-1:0] m;
    always_ff @(posedge clk) begin
        a <= a_in;                 // every clock: the core's stage flags say which values count
        b <= b_in;
        m <= a * b;
        if (ld_p) acc <= (first ? '0 : acc) + ACC_W'(m);       // zero the feedback, not the sum: one DSP slice
    end
endmodule
