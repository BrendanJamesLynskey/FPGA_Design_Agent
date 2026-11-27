// Sequencer of rp_patgen (architecture block seq).
// START (when RUNNING is 0) latches the run configuration, clears DONE and PERIODS_DONE,
// legalises WIDTH (written back to the register) and starts the phase or pattern counter.
// STOP ends the run at once. A run with CONT 0 completes when COUNT periods or passes have
// been emitted: the next sample slot then halts the run with DONE set and dac_a 0.
// Internal reset is active high. The latched copies take no reset (written at START).
module rp_seq (
    input  logic               clk,
    input  logic               rst,          // active high, synchronous
    input  logic               start_req,    // CTRL START written this clock
    input  logic               stop_req,     // CTRL STOP written this clock
    input  logic               cont,         // CONT live (pre-clock value)
    input  logic               mode,         // 0 pulse, 1 pattern
    input  logic        [31:0] period,       // PERIOD register (>= 2)
    input  logic        [31:0] width,        // WIDTH register (raw until START)
    input  logic signed [13:0] lvl_hi,
    input  logic signed [13:0] lvl_lo,
    input  logic        [15:0] count,        // COUNT register (1..65535)
    input  logic        [4:0]  pat_len,      // PAT_LEN register (1..16)
    input  logic        [15:0] sample_div,   // SAMPLE_DIV register (1..65535)
    input  logic        [223:0] pat,         // PAT0..PAT15, 14 bits each, PAT(i) = pat[14*i +: 14]
    output logic               running,
    output logic               done,
    output logic        [31:0] periods,      // PERIODS_DONE
    output logic               width_set,    // WIDTH register takes width_set_val this clock
    output logic        [31:0] width_set_val,
    output logic               load,         // a sample is emitted to out_limit this clock
    output logic               zero,         // out_limit forces dac_a to 0 this clock
    output logic               clr,          // out_limit clears CLAMPED this clock
    output logic signed [13:0] lvl           // level or sample to out_limit
);
    // ---------------------------------------------------------- start / stop
    wire start_go = start_req & ~stop_req & ~running & ~rst;

    // WIDTH legal at START: 1 .. PERIOD-1 (nearest legal value)
    wire [31:0] p_last = period - 32'd1;
    assign width_set_val = (width == 32'd0) ? 32'd1 :
                           (width > p_last) ? p_last : width;
    assign width_set = start_go;

    // ------------------------------------------------- latched run configuration
    logic        c_mode;
    logic [31:0] c_period;
    logic [31:0] c_width;
    logic signed [13:0] c_lh;
    logic signed [13:0] c_ll;
    logic [15:0] c_count;
    logic [4:0]  c_pl;
    logic [15:0] c_sd;
    logic [223:0] c_pat;

    // ---------------------------------------------------------- phase counters
    logic [31:0] ph;     // pulse phase (0..PERIOD-1) or pattern sample hold (0..SD-1)
    logic [4:0]  idx;    // pattern sample index (0..PL-1)

    wire [31:0] p_last_c  = c_period - 32'd1;
    wire [31:0] sd_last_c = {16'd0, c_sd} - 32'd1;
    wire        last_step = c_mode ? (ph == sd_last_c) : (ph == p_last_c);
    wire        pass_end  = last_step & (~c_mode | (idx == c_pl - 5'd1));

    // completion: CONT 0 and COUNT periods or passes already emitted
    wire at_end = ~cont & (periods >= {16'd0, c_count});
    wire emit   = running & ~stop_req & ~at_end;

    // sample for this clock
    logic [13:0] lvl_pat;
    always_comb begin
        lvl_pat = '0;
        for (int i = 0; i < 16; i++) begin
            if (idx[3:0] == i[3:0]) lvl_pat = c_pat[14*i +: 14];
        end
    end

    assign lvl  = c_mode ? $signed(lvl_pat) :
                  ((ph < c_width) ? c_lh : c_ll);
    assign load = emit;
    assign zero = stop_req | (running & at_end);
    assign clr  = start_go;

    // ---------------------------------------------------------- run state
    always_ff @(posedge clk) begin
        if (rst) begin
            running <= 1'b0;
            done    <= 1'b0;
            periods <= 32'd0;
        end else if (stop_req) begin
            running <= 1'b0;
            done    <= 1'b1;
        end else if (running) begin
            if (at_end) begin
                running <= 1'b0;
                done    <= 1'b1;
            end else if (pass_end) begin
                periods <= periods + 32'd1;
            end
        end else if (start_go) begin
            running <= 1'b1;
            done    <= 1'b0;
            periods <= 32'd0;
        end
    end

    // ------------------------------------------------ configuration latch, counters
    always_ff @(posedge clk) begin
        if (start_go) begin
            c_mode   <= mode;
            c_period <= period;
            c_width  <= width_set_val;
            c_lh     <= lvl_hi;
            c_ll     <= lvl_lo;
            c_count  <= count;
            c_pl     <= pat_len;
            c_sd     <= sample_div;
            c_pat    <= pat;
            ph       <= 32'd0;
            idx      <= 5'd0;
        end else if (emit) begin
            if (last_step) begin
                ph <= 32'd0;
                idx <= (idx == c_pl - 5'd1) ? 5'd0 : idx + 5'd1;
            end else begin
                ph <= ph + 32'd1;
            end
        end
    end
endmodule
