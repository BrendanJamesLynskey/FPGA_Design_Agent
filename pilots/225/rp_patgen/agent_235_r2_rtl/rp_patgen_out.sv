// rp_patgen_out: output stage. Clamps the sequencer sample to plus or minus
// the live LIMIT in the clock it is registered, sets CLAMPED on any cut
// (cleared by START), and registers dac_a, which is 0 unless RUNNING.
// rst is active high.
module rp_patgen_out (
    input  logic        clk,
    input  logic        rst,
    input  logic        running,
    input  logic        stop_req,
    input  logic        start_eff,
    input  logic        sv,
    input  logic [13:0] sval,
    input  logic [12:0] limit,
    output logic [13:0] dac,
    output logic        clamped
);
    wire [14:0] v    = {sval[13], sval};            // 15-bit signed
    wire [14:0] mag  = v[14] ? (15'd0 - v) : v;     // magnitude, fits 15 bits
    wire [14:0] lim  = {2'd0, limit};
    wire        cut  = (mag > lim);
    wire [13:0] lim_n = {1'b0, limit};
    wire [13:0] clip = sval[13] ? (14'd0 - lim_n) : lim_n;
    wire        run_val = running & sv & ~stop_req;
    wire        cut_now = run_val & cut;

    always_ff @(posedge clk) begin
        if (rst) begin
            dac     <= 14'd0;
            clamped <= 1'b0;
        end else begin
            dac <= run_val ? (cut ? clip : sval) : 14'd0;
            if (start_eff)
                clamped <= 1'b0;
            else if (cut_now)
                clamped <= 1'b1;
        end
    end
endmodule
