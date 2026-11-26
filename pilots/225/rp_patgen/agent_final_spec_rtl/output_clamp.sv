// Output stage: clips the selected level or sample to the range minus LIMIT to plus LIMIT
// (LIMIT as it was on the clock of the sample), registers it, and gates dac_a with RUNNING.
// Sets the sticky CLAMPED flag when a value driven to dac_a is cut. Synchronous reset.
module output_clamp (
    input  logic        clk,
    input  logic        rst,
    input  logic        start_go,
    input  logic        running_i,
    input  logic        emit_valid,
    input  logic [13:0] raw_i,
    input  logic [12:0] limit_i,
    output logic [13:0] dac_a,
    output logic        clamped_q
);
    wire signed [14:0] raw15  = $signed({raw_i[13], raw_i});
    wire signed [14:0] lim15  = $signed({2'b00, limit_i});
    wire signed [14:0] nlim15 = 15'sd0 - lim15;
    wire [13:0]        lim14  = {1'b0, limit_i};
    wire [13:0]        nlim14 = 14'd0 - lim14;

    wire over_hi = (raw15 > lim15);
    wire over_lo = (raw15 < nlim15);
    wire over    = over_hi | over_lo;
    wire [13:0] clipped = over_hi ? lim14 : (over_lo ? nlim14 : raw_i);

    logic [13:0] dac_q;

    // the clip uses the LIMIT of the clock the sample is selected on (registered here)
    always_ff @(posedge clk) begin
        dac_q <= emit_valid ? clipped : 14'd0;
    end

    assign dac_a = running_i ? dac_q : 14'd0;

    always_ff @(posedge clk) begin
        if (rst | start_go) clamped_q <= 1'b0;
        else if (emit_valid & over) clamped_q <= 1'b1;
    end
endmodule
