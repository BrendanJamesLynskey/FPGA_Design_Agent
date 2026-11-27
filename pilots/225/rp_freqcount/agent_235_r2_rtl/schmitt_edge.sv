// Schmitt trigger edge detector on adc_a (rp_freqcount).
// Armed when the sample is at or below thr_lo; a rising edge is counted when the
// sample is at or above thr_hi while armed, then disarmed. Samples between the
// thresholds change nothing. Disabled (no edge) when thr_hi <= thr_lo.
// Runs every clk; the gate sequencer decides whether a counted edge is kept.
// Synchronous reset (rst is active high, inverted once at the top).
module schmitt_edge (
    input  logic              clk,
    input  logic              rst,
    input  logic signed [13:0] s,       // adc_a sample, counts
    input  logic signed [13:0] thr_hi,  // THR_HIGH, effective this clk
    input  logic signed [13:0] thr_lo,  // THR_LOW, effective this clk
    output logic              edge_o    // one counted rising edge in this clk
);
    logic armed;
    logic bad;
    logic hi_hit;
    logic lo_hit;

    assign bad    = (thr_hi <= thr_lo);
    assign hi_hit = (s >= thr_hi);
    assign lo_hit = (s <= thr_lo);
    assign edge_o = armed & hi_hit & ~bad;

    always_ff @(posedge clk) begin
        if (rst) begin
            armed <= 1'b0;
        end else if (edge_o) begin
            armed <= 1'b0;
        end else if (lo_hit) begin
            armed <= 1'b1;
        end
    end
endmodule
