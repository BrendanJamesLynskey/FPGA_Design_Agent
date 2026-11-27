// Output stage of rp_patgen (architecture block out_limit).
// Cuts every level or sample to -LIMIT..+LIMIT, sets CLAMPED on any cut since START,
// and registers dac_a one clock after the internal level changes. dac_a is forced to 0
// by STOP or by the completion of a sequence (zero).
// Internal reset is active high (inverted once at the top of rp_patgen).
module rp_out_limit (
    input  logic               clk,
    input  logic               rst,       // active high, synchronous
    input  logic               load,      // a new level or sample is emitted this clock
    input  logic               zero,      // force dac_a to 0 this clock (STOP or completion)
    input  logic               clr,       // START accepted: clear CLAMPED
    input  logic signed [13:0] lvl,       // level or sample before the cut
    input  logic        [12:0] limit,     // LIMIT register in force, magnitude 0..7372
    output logic signed [13:0] dac,       // registered OUT1 sample
    output logic               clamped    // a cut happened since START
);
    wire signed [14:0] s_lvl = {lvl[13], lvl};
    wire signed [14:0] s_hi  = {2'b00, limit};
    wire signed [14:0] s_lo  = -s_hi;
    wire signed [13:0] lim_p = {1'b0, limit};
    wire signed [13:0] lim_n = -lim_p;
    wire               over_hi = (s_lvl > s_hi);
    wire               over_lo = (s_lvl < s_lo);

    always_ff @(posedge clk) begin
        if (rst) begin
            dac     <= '0;
            clamped <= 1'b0;
        end else begin
            if (clr) begin
                clamped <= 1'b0;
            end
            if (zero) begin
                dac <= '0;
            end else if (load) begin
                if (over_hi) begin
                    dac     <= lim_p;
                    clamped <= 1'b1;
                end else if (over_lo) begin
                    dac     <= lim_n;
                    clamped <= 1'b1;
                end else begin
                    dac <= lvl;
                end
            end
        end
    end
endmodule
