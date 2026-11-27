// p5_wr_side: clk_c3 writer. PRBS-31 words into the FIFO, one per clock while RUN and not full.
// Counters (32 bit, wrap): WORDS_W, OVERFLOWS, STALL_W; OCC_MAX saturating maximum of the write-side fill.
module p5_wr_side #(
    parameter int          CW        = 10,
    parameter logic [30:0] PRBS_SEED = 31'h7FFFFFFF,
    parameter int          DEPTH     = 512
) (
    input  logic          clk,
    input  logic          rst,
    input  logic          run,
    input  logic          blocked,     // CLEAR sequence in progress: no writes
    input  logic          clr,         // one-clock pulse: zero counters, reload seed
    input  logic          full,        // FIFO full or in reset (full | wr_rst_busy)
    input  logic          ovf_flag,    // FIFO overflow strobe
    input  logic [CW-1:0] fill,        // write-side fill level
    input  logic          fill_ok,     // FIFO not in reset (~wr_rst_busy): fill is valid, writes allowed
    output logic          wr_en,
    output logic [31:0]   din,
    output logic [31:0]   words_w,
    output logic [31:0]   overflows,
    output logic [31:0]   stall_w,
    output logic [CW-1:0] occ_max
);
    logic [30:0] st;
    logic [30:0] st_next;
    logic [31:0] word;
    logic        idle_ok;

    prbs31_step u_prbs (.state(st), .state_next(st_next), .word(word));

    // a FIFO in reset is not "full": the writer just waits, STALL_W does not count
    assign idle_ok = ~blocked & fill_ok;
    assign wr_en   = run & ~full & idle_ok;
    assign din     = word;

    always_ff @(posedge clk) begin
        if (rst || clr) begin
            st        <= PRBS_SEED;
            words_w   <= 32'd0;
            overflows <= 32'd0;
            stall_w   <= 32'd0;
            occ_max   <= '0;
        end else begin
            if (wr_en) begin
                st      <= st_next;
                words_w <= words_w + 32'd1;
            end
            if (run && full && idle_ok) stall_w   <= stall_w + 32'd1;
            if (ovf_flag)               overflows <= overflows + 32'd1;
            if (idle_ok && fill > occ_max)
                occ_max <= (fill > CW'(DEPTH)) ? CW'(DEPTH) : fill;
        end
    end
endmodule
