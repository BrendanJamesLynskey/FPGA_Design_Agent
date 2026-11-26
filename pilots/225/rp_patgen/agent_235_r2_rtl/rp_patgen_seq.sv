// rp_patgen_seq: pulse and pattern sequencer. Owns RUNNING, DONE and
// PERIODS_DONE. One signed sample per clock goes to the stage register
// (sv, sval), which the output stage clamps and registers as dac_a.
// The pulse counter and the pattern index share ca. STOP wins over START;
// START while RUNNING is ignored (the regs block does not pulse start_eff then).
// rst is active high.
module rp_patgen_seq (
    input  logic        clk,
    input  logic        rst,
    input  logic        start_eff,
    input  logic        stop_req,
    input  logic        run_mode,
    input  logic [31:0] run_period,
    input  logic [31:0] run_width,
    input  logic [13:0] run_hi,
    input  logic [13:0] run_lo,
    input  logic [15:0] run_count,
    input  logic        run_cont,
    input  logic [4:0]  run_pat_len,
    input  logic [15:0] run_div,
    output logic [3:0]  pat_idx,
    input  logic [13:0] pat_val,
    output logic        running,
    output logic        done,
    output logic [31:0] pdone,
    output logic        sv,
    output logic [13:0] sval
);
    logic        seq_active;
    logic [31:0] ca;
    logic [15:0] cb;

    assign pat_idx = ca[3:0];

    wire [31:0] ca_p1    = ca + 32'd1;
    wire [15:0] cb_p1    = cb + 16'd1;
    wire [4:0]  ca5_p1   = ca[4:0] + 5'd1;
    wire        div_wrap = (cb_p1 >= run_div);
    wire        pul_wrap = (ca_p1 >= run_period);
    wire        pat_wrap = div_wrap & (ca5_p1 >= run_pat_len);
    wire        wrap     = run_mode ? pat_wrap : pul_wrap;
    wire        adv      = run_mode ? div_wrap : 1'b1;
    wire [13:0] sample   = run_mode ? pat_val :
                           ((ca < run_width) ? run_hi : run_lo);
    wire [31:0] pdone_inc = (pdone == 32'hFFFFFFFF) ? pdone : pdone + 32'd1;
    wire        end_seq   = wrap & ~run_cont & (pdone_inc >= {16'd0, run_count});

    // control state
    always_ff @(posedge clk) begin
        if (rst) begin
            running    <= 1'b0;
            done       <= 1'b0;
            seq_active <= 1'b0;
            sv         <= 1'b0;
            pdone      <= 32'd0;
        end else if (stop_req) begin
            running    <= 1'b0;
            done       <= 1'b1;
            seq_active <= 1'b0;
            sv         <= 1'b0;
        end else if (start_eff) begin
            running    <= 1'b1;
            done       <= 1'b0;
            seq_active <= 1'b1;
            sv         <= 1'b0;
            pdone      <= 32'd0;
        end else if (running) begin
            if (seq_active) begin
                sv <= 1'b1;
                if (wrap) begin
                    pdone <= pdone_inc;
                    if (end_seq) seq_active <= 1'b0;
                end
            end else begin
                sv <= 1'b0;
                if (~sv) begin
                    running <= 1'b0;
                    done    <= 1'b1;
                end
            end
        end
    end

    // position counters (cleared at START, no reset needed)
    always_ff @(posedge clk) begin
        if (start_eff) begin
            ca <= 32'd0;
            cb <= 16'd0;
        end else if (~stop_req & running & seq_active) begin
            ca <= adv ? (wrap ? 32'd0 : ca_p1) : ca;
            cb <= run_mode ? (div_wrap ? 16'd0 : cb_p1) : 16'd0;
        end
    end

    // stage sample; only used when sv is high
    always_ff @(posedge clk) begin
        sval <= sample;
    end
endmodule
