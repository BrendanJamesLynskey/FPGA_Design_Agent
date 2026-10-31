// pdm_stats.sv: clocks a PDM microphone and counts, over a window of N bits,
// how many bits were 1 and how many times the bit changed. It does not
// decimate: the counts are enough to tell a live microphone (about half ones,
// frequent changes) from a dead or stuck line.
//
// M_CLK is HALF clocks low and HALF high (21 = 2.381 MHz at 100 MHz) and runs
// from reset, so the microphone is awake (wake-up <= 20 ms) before a count
// starts. With L/R select low the microphone drives DATA after each falling
// edge; DATA is sampled in the middle of the high half.

module pdm_stats #(
    parameter int HALF = 21
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        go,
    input  logic [31:0] nbits,      // window length in PDM bits (0 is taken as 1)
    output logic        busy,
    output logic        done,
    output logic [31:0] ones,
    output logic [31:0] changes,
    output logic        mclk,
    input  logic        mdata       // synchronised
);
    logic [15:0] div;
    logic [31:0] left;
    logic        prev, have_prev, sample;

    // divider: mclk toggles every HALF clocks; sample once per period, HALF/2 clocks after the rise
    always_ff @(posedge clk) begin
        if (rst) begin
            div <= '0; mclk <= 1'b0;
        end else if (div == 16'(HALF - 1)) begin
            div <= '0; mclk <= ~mclk;
        end else begin
            div <= div + 16'd1;
        end
    end
    assign sample = mclk && div == 16'(HALF / 2);

    always_ff @(posedge clk) begin
        if (rst) begin
            busy <= 1'b0; done <= 1'b0; ones <= '0; changes <= '0; left <= '0; prev <= 1'b0; have_prev <= 1'b0;
        end else if (!busy) begin
            if (go) begin
                busy <= 1'b1; done <= 1'b0; ones <= '0; changes <= '0; have_prev <= 1'b0;
                left <= (nbits == 32'd0) ? 32'd1 : nbits;
            end
        end else if (sample) begin
            ones      <= ones + {31'd0, mdata};
            changes   <= changes + {31'd0, have_prev && (mdata != prev)};
            prev      <= mdata;
            have_prev <= 1'b1;
            left      <= left - 32'd1;
            if (left == 32'd1) begin busy <= 1'b0; done <= 1'b1; end
        end
    end
endmodule
