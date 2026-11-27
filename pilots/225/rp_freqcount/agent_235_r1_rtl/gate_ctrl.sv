// gate_ctrl: gate sequencer, edge and span accumulation, result latch.
// A START (strobe while not busy) starts a gate of gate_len cycles. The gate
// samples are the cycles after START, the last one being the latch cycle.
// On the latch cycle EDGES, GATE_ACTUAL, SPAN, FEW_EDGES, BAD_THRESH, DONE and
// MEAS_DONE are updated together. With cont set the next gate starts on the
// cycle after the latch and DONE stays set. Control and result registers take
// the synchronous reset rst (active high); working registers take none and are
// loaded at START.
module gate_ctrl (
    input  logic        clk,
    input  logic        rst,
    input  logic        start,      // START write strobe this cycle (bus decoded)
    input  logic        cont,       // CTRL bit 1 register
    input  logic [31:0] gate_len,   // GATE_LEN register (already clamped to >= minimum)
    input  logic        good,       // thr_h > thr_l (no BAD_THRESH)
    input  logic        edge_p,     // counted rising edge on this sample
    output logic        busy,
    output logic        done,
    output logic        few,
    output logic        bad,
    output logic [31:0] edges,
    output logic [31:0] gate_actual,
    output logic [31:0] span,
    output logic [31:0] meas_done
);
    // working registers (no reset: loaded at START before use)
    logic [31:0] g_cnt;
    logic [31:0] g_len;
    logic [31:0] a_edges;
    logic [31:0] a_first;
    logic [31:0] a_last;

    logic [31:0] cnt_now;
    logic        edge_now;
    logic        last;
    logic [31:0] a_edges_n;
    logic [31:0] first_n;
    logic [31:0] last_n;
    logic        start_ok;

    assign cnt_now   = g_cnt + 32'd1;          // 1-based sample index in the gate
    assign edge_now  = busy & edge_p;
    assign last      = busy & (cnt_now == g_len);
    assign a_edges_n = a_edges + {31'd0, edge_now};
    assign first_n   = (edge_now && (a_edges == 32'd0)) ? cnt_now : a_first;
    assign last_n    = edge_now ? cnt_now : a_last;
    assign start_ok  = start & ~busy;

    // working datapath: no reset
    always_ff @(posedge clk) begin
        if (start_ok) begin
            g_cnt   <= 32'd0;
            g_len   <= gate_len;
            a_edges <= 32'd0;
        end else if (busy) begin
            if (last) begin
                g_cnt   <= 32'd0;
                a_edges <= 32'd0;
                if (cont) begin
                    g_len <= gate_len;   // next gate starts on the cycle after this latch
                end
            end else begin
                g_cnt   <= cnt_now;
                a_edges <= a_edges_n;
                a_first <= first_n;
                a_last  <= last_n;
            end
        end
    end

    // control and result registers: synchronous reset
    always_ff @(posedge clk) begin
        if (rst) begin
            busy        <= 1'b0;
            done        <= 1'b0;
            few         <= 1'b0;
            bad         <= 1'b0;
            edges       <= 32'd0;
            gate_actual <= 32'd0;
            span        <= 32'd0;
            meas_done   <= 32'd0;
        end else if (start_ok) begin
            busy <= 1'b1;
            done <= 1'b0;
        end else if (busy && last) begin
            edges       <= a_edges_n;
            gate_actual <= g_len;
            span        <= (a_edges_n >= 32'd2) ? (last_n - first_n) : 32'd0;
            few         <= (a_edges_n < 32'd2);
            bad         <= ~good;
            meas_done   <= meas_done + 32'd1;
            done        <= 1'b1;
            busy        <= cont;
        end
    end
endmodule
