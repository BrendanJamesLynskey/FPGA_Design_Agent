// Sequencer: START/STOP state, latched configuration, pulse phase counter,
// pattern sample and hold counters, PERIODS_DONE (saturating), DONE and RUNNING.
// Reset is active high and synchronous; only the control state is reset.
module sequencer (
    input  logic         clk,
    input  logic         rst,
    input  logic         start_go,
    input  logic         stop_req,
    input  logic         cont_new,
    input  logic [31:0]  period_i,
    input  logic [31:0]  width_i,
    input  logic         mode_i,
    input  logic [15:0]  count_i,
    input  logic [4:0]   patlen_i,
    input  logic [15:0]  sdiv_i,
    input  logic [13:0]  lvl_hi_i,
    input  logic [13:0]  lvl_lo_i,
    input  logic [223:0] pat_i,
    output logic         running_o,
    output logic         done_o,
    output logic [31:0]  periods_o,
    output logic         emit_valid_o,
    output logic [13:0]  raw_o
);
    logic        running_q, done_q, ending_q;
    logic [1:0]  pend_q;
    logic [31:0] periods_q;
    logic [31:0] p_q;
    logic [15:0] h_q;
    logic [3:0]  idx_q;
    logic [31:0] period_l, width_l;
    logic        mode_l, cont_l;
    logic [15:0] count_l, sdiv_l;
    logic [4:0]  patlen_l;
    logic [13:0] pat_arr [0:15];

    genvar g;
    generate
        for (g = 0; g < 16; g++) begin : g_pat_in
            assign pat_arr[g] = pat_i[g*14 +: 14];
        end
    endgenerate

    wire emit_valid = running_q & ~ending_q & (pend_q != 2'd2);

    // pulse: phase counter over PERIOD clocks, level HI for the first WIDTH clocks
    wire [32:0] p_inc    = {1'b0, p_q} + 33'd1;
    wire        p_last   = (p_inc >= {1'b0, period_l});
    wire [13:0] pulse_raw = (p_q < width_l) ? lvl_hi_i : lvl_lo_i;

    // pattern: hold counter over SAMPLE_DIV clocks, index over PAT_LEN samples
    wire [16:0] h_inc    = {1'b0, h_q} + 17'd1;
    wire        h_last   = (h_inc >= {1'b0, sdiv_l});
    wire [5:0]  idx_inc  = {2'b00, idx_q} + 6'd1;
    wire        idx_last = (idx_inc >= {1'b0, patlen_l});
    wire [13:0] pat_raw  = pat_arr[idx_q];

    wire        pass_end   = mode_l & h_last & idx_last;
    wire        pulse_end  = ~mode_l & p_last;
    wire        period_end = pulse_end | pass_end;

    wire [31:0] periods_sat = (periods_q == 32'hFFFF_FFFF) ? periods_q : (periods_q + 32'd1);
    wire        end_now     = period_end & ~cont_l & (periods_sat >= {16'd0, count_l});

    assign raw_o        = mode_l ? pat_raw : pulse_raw;
    assign running_o    = running_q;
    assign done_o       = done_q;
    assign periods_o    = periods_q;
    assign emit_valid_o = emit_valid;

    // control: emit side first, then the write side (STOP wins, START only when stopped)
    always_ff @(posedge clk) begin
        if (rst) begin
            running_q <= 1'b0;
            done_q    <= 1'b0;
            ending_q  <= 1'b0;
            pend_q    <= 2'd0;
            periods_q <= 32'd0;
        end else begin
            if (ending_q) begin
                running_q <= 1'b0;
                done_q    <= 1'b1;
                ending_q  <= 1'b0;
            end else if (running_q) begin
                if (pend_q == 2'd2) begin
                    pend_q <= 2'd1;
                end else begin
                    pend_q <= 2'd0;
                    if (period_end) begin
                        periods_q <= periods_sat;
                        if (end_now) ending_q <= 1'b1;
                    end
                end
            end
            if (stop_req) begin
                running_q <= 1'b0;
                done_q    <= 1'b1;
                pend_q    <= 2'd0;
                ending_q  <= 1'b0;
            end else if (start_go) begin
                running_q <= 1'b1;
                done_q    <= 1'b0;
                pend_q    <= 2'd2;
                ending_q  <= 1'b0;
                periods_q <= 32'd0;
            end
        end
    end

    // latched configuration and counters: datapath, not reset
    always_ff @(posedge clk) begin
        if (start_go) begin
            period_l <= period_i;
            width_l  <= width_i;
            mode_l   <= mode_i;
            count_l  <= count_i;
            cont_l   <= cont_new;
            patlen_l <= patlen_i;
            sdiv_l   <= sdiv_i;
            p_q      <= 32'd0;
            h_q      <= 16'd0;
            idx_q    <= 4'd0;
        end else if (emit_valid) begin
            if (~mode_l) begin
                p_q <= p_last ? 32'd0 : p_inc[31:0];
            end else begin
                h_q <= h_last ? 16'd0 : h_inc[15:0];
                if (h_last) idx_q <= idx_last ? 4'd0 : idx_inc[3:0];
            end
        end
    end
endmodule
