// p5_rd_side: gt_refclk reader. Reads one word whenever the FIFO is not empty (one per DIV clocks in SLOW_READ),
// checks it against its own PRBS-31 copy. A mismatch counts in DATA_ERRS; the expected sequence advances either way.
// The FIFO is read in standard mode: dout is valid the clock after rd_en.
module p5_rd_side #(
    parameter logic [30:0] PRBS_SEED = 31'h7FFFFFFF,
    parameter int          DIV       = 8
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        slow,       // synchronised SLOW_READ
    input  logic        inject,     // one-clock pulse: flip bit 0 of the next received word
    input  logic        clr,        // one-clock pulse: zero counters, reload seed
    input  logic        empty,
    input  logic        rd_busy,    // FIFO in reset
    input  logic [31:0] dout,
    input  logic        unf_flag,   // FIFO underflow strobe
    output logic        rd_en,
    output logic [31:0] words_r,
    output logic [31:0] data_errs,
    output logic [31:0] underflows,
    output logic        err_seen
);
    localparam int DW = (DIV > 1) ? $clog2(DIV) : 1;

    logic [30:0]   st;
    logic [30:0]   st_next;
    logic [31:0]   exp_word;
    logic [DW-1:0] slow_cnt;
    logic          slow_ok;
    logic          rd_v;
    logic          inj_pend;
    logic [31:0]   got;

    prbs31_step u_prbs (.state(st), .state_next(st_next), .word(exp_word));

    assign slow_ok = !slow || (slow_cnt == DW'(DIV - 1));
    assign rd_en   = !empty && !rd_busy && slow_ok;
    assign got     = {dout[31:1], dout[0] ^ inj_pend};

    always_ff @(posedge clk) begin
        if (rst) begin
            rd_v       <= 1'b0;
            inj_pend   <= 1'b0;
            slow_cnt   <= DW'(DIV - 1);
            st         <= PRBS_SEED;
            words_r    <= 32'd0;
            data_errs  <= 32'd0;
            underflows <= 32'd0;
            err_seen   <= 1'b0;
        end else begin
            rd_v <= rd_en;
            if (!slow)            slow_cnt <= DW'(DIV - 1);
            else if (rd_en)       slow_cnt <= '0;
            else if (!slow_ok)    slow_cnt <= slow_cnt + 1'b1;
            if (unf_flag) underflows <= underflows + 32'd1;
            if (rd_v) begin
                st       <= st_next;
                words_r  <= words_r + 32'd1;
                inj_pend <= 1'b0;
                if (got != exp_word) data_errs <= data_errs + 32'd1;
            end
            if (inject) inj_pend <= 1'b1;
            if (clr) begin
                st         <= PRBS_SEED;
                words_r    <= 32'd0;
                data_errs  <= 32'd0;
                underflows <= 32'd0;
            end
            err_seen <= (data_errs != 32'd0);
        end
    end
endmodule
