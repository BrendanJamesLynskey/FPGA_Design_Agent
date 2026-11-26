// schmitt_edge: Schmitt trigger on adc_a with one-cycle rising-edge pulses.
// Armed when a sample is at or below thr_l; a sample above thr_h while armed
// counts one rising edge (edge_p, combinational on the sampling edge) and disarms.
// The armed state persists across gates and is cleared only by reset.
// When thr_h <= thr_l (BAD_THRESH) no edge is produced.
// Single clock domain (clk); rst is active high, synchronous, inverted once at the top.
module schmitt_edge #(
    parameter int ADC_WIDTH = 14
) (
    input  logic                       clk,
    input  logic                       rst,
    input  logic signed [ADC_WIDTH-1:0] adc_a,
    input  logic signed [ADC_WIDTH-1:0] thr_h,
    input  logic signed [ADC_WIDTH-1:0] thr_l,
    output logic                       edge_p
);
    logic armed;
    logic good;
    logic above_h;
    logic at_or_below_l;

    assign good         = (thr_h > thr_l);
    assign above_h      = (adc_a > thr_h);
    assign at_or_below_l = (adc_a <= thr_l);
    assign edge_p       = good & above_h & armed;

    always_ff @(posedge clk) begin
        if (rst) begin
            armed <= 1'b0;
        end else if (edge_p) begin
            armed <= 1'b0;
        end else if (at_or_below_l) begin
            armed <= 1'b1;
        end
    end
endmodule
