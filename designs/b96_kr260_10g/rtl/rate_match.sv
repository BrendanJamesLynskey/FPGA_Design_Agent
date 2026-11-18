// rate_match.sv: the receive-to-core elastic buffer of brief 96C. It carries the PCS's decoded blocks from the receive user clock (the
// clock the GT recovers from the line: the partner's frequency) to the core clock (TXUSRCLK2: ours), which differ by up to +-100 ppm
// on a real link (IEEE 802.3 clause 49), and keeps the fill level bounded by inserting or deleting IDLE blocks BETWEEN frames only.
// docs/design.md section 9 and model/ratematch.py (the twin, compared output for output in the bench) say the same thing in words.
//
//   write side (wclk): every valid block is stored, with two flags computed on the way in (pure idle; ordered set). When the buffer is
//     full as this side sees it (the read pointer it sees is old: conservative) the block is dropped and counted (n_ovf).
//   read side (rclk): at most one block a clock, in 32 of 33 clocks (slot clocks; the 33rd is the pause clock, the transmit gearbox's cadence):
//     slot, a block visible       -> pop it and output it;
//     slot, none, not in a frame  -> insert one idle block (n_ins);
//     slot, none, inside a frame  -> output nothing, one clock (n_stall; the MAC holds its state, nothing is lost);
//     pause clock, visible fill > HI, not in a frame, at least MIN_KEEP pure idles just output, head is a pure idle -> delete it (n_del).
//   "inside a frame" = the last block output was a start block (lane 0 or 4) or a data block. A pure idle block is an all-idle control
//   block that is not an ordered set. Ordered sets (link fault signalling), error blocks, terminate blocks and anything with data are
//   never inserted, duplicated or deleted, so a frame is never touched and a Local/Remote Fault ordered set is never dropped.
//   While the synchronised block lock is low the reader discards the buffer's content, one block a clock, and outputs nothing.
// The pointers cross as gray codes through xpm_cdc_gray (never reset: the write pointer only moves when a block is written and the read
// pointer follows it); the block memory is read in the read domain only while at least one block is visible, i.e. at least
// DEST_SYNC_FF + 1 read clocks after it was written.
// Registered output: r_v/r_d/r_c/r_lock. Latency write edge -> output: gray register (1) + DEST_SYNC_FF + WP_REG + decision/output (1) read clocks.
module rate_match #(
    parameter int AW       = 4,     // 2**AW blocks
    parameter int HI       = 4,     // delete idles while the visible fill is above this
    parameter int MIN_KEEP = 1,     // delete only after this many consecutive pure idle blocks were output
    parameter int WP_REG   = 1,     // 1: register the decoded write pointer in the read domain (a clock more, easier timing)
    parameter int RP_REG   = 1      // the same for the read pointer in the write domain
) (
    input  logic        wclk,
    input  logic        w_v,        // a decoded block this clock
    input  logic [63:0] w_d,
    input  logic [7:0]  w_c,
    input  logic        w_os,       // the block was an ordered set (shown by the decoder as idles)
    input  logic        w_lock,     // PCS block lock (write domain)
    input  logic        clr_w,      // clear the write-side counter (write domain pulse)
    output logic [31:0] n_ovf, n_wr,
    input  logic        rclk,
    input  logic        rrst,
    input  logic        clr_r,      // clear the read-side counters (read domain pulse)
    output logic        r_v,
    output logic [63:0] r_d,
    output logic [7:0]  r_c,
    output logic        r_lock,
    output logic [31:0] n_ins, n_del, n_stall, n_out, n_drain, fill_min, fill_max
);
    localparam int DEPTH = 1 << AW;
    localparam int PW = AW + 1;
    // entry: {pure idle, ordered set, c[7:0], d[63:0]}
    (* ram_style = "distributed" *) logic [73:0] mem [0:DEPTH - 1];
    logic [PW - 1:0] wptr = '0, rptr = '0;
    logic [PW - 1:0] wp_s, rp_s;
    logic            lock_s, wfull;
    logic [73:0]     w_ent;
    assign w_ent = {(w_c == 8'hFF) && (w_d == 64'h0707070707070707) && !w_os, w_os, w_c, w_d};
    assign wfull = ((wptr - rp_s) >= PW'(DEPTH));

    always_ff @(posedge wclk) begin
        if (w_v) begin
            if (wfull) n_ovf <= n_ovf + 32'd1;
            else begin mem[wptr[AW - 1:0]] <= w_ent; wptr <= wptr + PW'(1); n_wr <= n_wr + 32'd1; end
        end
        if (clr_w) begin n_ovf <= '0; n_wr <= '0; end        // a clear wins over a count in the same clock
    end
    initial begin n_ovf = '0; n_wr = '0; for (int i = 0; i < DEPTH; i++) mem[i] = '0; end

    xpm_cdc_gray #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .REG_OUTPUT(WP_REG), .SIM_ASSERT_CHK(0), .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(PW)) u_wp (
        .src_clk(wclk), .src_in_bin(wptr), .dest_clk(rclk), .dest_out_bin(wp_s));
    xpm_cdc_gray #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .REG_OUTPUT(RP_REG), .SIM_ASSERT_CHK(0), .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(PW)) u_rp (
        .src_clk(rclk), .src_in_bin(rptr), .dest_clk(wclk), .dest_out_bin(rp_s));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_lk (
        .src_clk(1'b0), .src_in(w_lock), .dest_clk(rclk), .dest_out(lock_s));

    // ---------------------------------------------------------------- read side
    logic [PW - 1:0] fill;
    logic [73:0]     head;
    logic            slot, in_frame, head_idle, head_frame;
    logic [5:0]      pace;
    logic [1:0]      idle_run;
    assign fill = wp_s - rptr;
    assign head = mem[rptr[AW - 1:0]];
    assign slot = (pace != 6'd32);
    assign head_idle = head[73];
    // a start block (lane 0 or lane 4) or a data block leaves the stream inside a frame
    assign head_frame = (head[71:64] == 8'h00) || (head[71:64] == 8'h01 && head[7:0] == 8'hFB) || (head[71:64] == 8'h1F && head[39:32] == 8'hFB);
    initial begin
        n_ins = '0; n_del = '0; n_stall = '0; n_out = '0; n_drain = '0; fill_min = '1; fill_max = '0; r_v = 1'b0; r_d = '0; r_c = '0; r_lock = 1'b0;
    end
    always_ff @(posedge rclk) begin
        r_v <= 1'b0;
        if (rrst) begin
            rptr <= wp_s; pace <= '0; in_frame <= 1'b0; idle_run <= '0; r_lock <= 1'b0; r_d <= '0; r_c <= '0;
            n_ins <= '0; n_del <= '0; n_stall <= '0; n_out <= '0; n_drain <= '0; fill_min <= '1; fill_max <= '0;
        end else begin
            pace <= (pace == 6'd32) ? 6'd0 : pace + 6'd1;
            r_lock <= lock_s;
            if (!lock_s) begin
                in_frame <= 1'b0; idle_run <= '0;
                if (fill != '0) begin rptr <= rptr + PW'(1); n_drain <= n_drain + 32'd1; end
            end else if (slot) begin
                if (32'(fill) < fill_min) fill_min <= 32'(fill);
                if (32'(fill) > fill_max) fill_max <= 32'(fill);
                if (fill != '0) begin
                    r_v <= 1'b1; r_d <= head[63:0]; r_c <= head[71:64]; rptr <= rptr + PW'(1);
                    in_frame <= head_frame;
                    idle_run <= head_idle ? ((idle_run == 2'd3) ? 2'd3 : idle_run + 2'd1) : 2'd0;
                    n_out <= n_out + 32'd1;
                end else if (!in_frame) begin
                    r_v <= 1'b1; r_d <= 64'h0707070707070707; r_c <= 8'hFF;
                    idle_run <= (idle_run == 2'd3) ? 2'd3 : idle_run + 2'd1;
                    n_ins <= n_ins + 32'd1; n_out <= n_out + 32'd1;
                end else n_stall <= n_stall + 32'd1;
            end else begin
                if (fill > PW'(HI) && !in_frame && idle_run >= 2'(MIN_KEEP) && head_idle) begin
                    rptr <= rptr + PW'(1); n_del <= n_del + 32'd1;
                end
            end
            if (clr_r) begin n_ins <= '0; n_del <= '0; n_stall <= '0; n_out <= '0; n_drain <= '0; fill_min <= '1; fill_max <= '0; end     // a clear wins over a count in the same clock
        end
    end
endmodule
