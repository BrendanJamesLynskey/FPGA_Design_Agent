// fir_mac: one multiply-accumulate engine of the folded FIR (brief 63A): operand registers (the DSP slice's A and B),
// the product register (M) and the accumulator (P). use_dsp sits on this module only, so the DSP slices take the
// multiply-accumulates and nothing else (on the whole folded core it also pulled the adder tree, counters and
// comparators into DSP slices: 21 slices for 4 engines in the first characterisation run).
(* use_dsp = "yes" *)
module fir_mac #(
    parameter int DATA_W = 16,
    parameter int COEF_W = 16,
    parameter int ACC_W  = 36
) (
    input  logic                     clk,
    input  logic                     ld_ab,      // capture the operands
    input  logic                     ld_m,       // capture the product
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
        if (ld_ab) begin
            a <= a_in;
            b <= b_in;
        end
        if (ld_m) m <= a * b;
        if (ld_p) acc <= first ? ACC_W'(m) : acc + ACC_W'(m);
    end
endmodule
