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
// The blocks cross in AMD's own asynchronous FIFO macro xpm_fifo_async (16 words, distributed RAM, first-word-fall-through, read data count): the macro
// carries the pointers, the memory and their clock-crossing constraints, so report_cdc is clean (a hand-made block memory read in the other clock gives
// CDC-1 Critical, measured in brief 96C). The policy below runs on its `empty` flag and read data count (the words the read side can see; it lags the writer by the macro's
// synchroniser, so the true fill is a few blocks higher).
// Registered output: r_v/r_d/r_c/r_lock.
module rate_match #(
    parameter int AW       = 4,     // 2**AW blocks (16 is the macro's minimum)
    parameter int HI       = 4,     // delete idles while the visible fill is above this
    parameter int MIN_KEEP = 0      // delete only after this many consecutive pure idle blocks were output (0: a lone idle block between frames may go; see docs/design.md section 9)
) (
    input  logic        wclk,
    input  logic        wrst,       // write-domain reset (receive side down): resets the FIFO macro
    input  logic        w_v,        // a decoded block this clock
    input  logic [63:0] w_d,
    input  logic [7:0]  w_c,
    input  logic        w_os,       // the block was an ordered set (shown by the decoder as idles)
    input  logic        w_lock,     // PCS block lock (write domain)
    input  logic        clr_w,      // clear the write-side counters (write domain pulse)
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
    localparam int CW = AW + 1;
    logic [73:0]   w_ent, head;
    logic          lock_s, f_full, f_empty, wbusy, rbusy, rd_en, wr_en;
    logic [CW-1:0] fill;
    assign w_ent = {(w_c == 8'hFF) && (w_d == 64'h0707070707070707) && !w_os, w_os, w_c, w_d};
    assign wr_en = w_v && !f_full && !wbusy;
    xpm_fifo_async #(.CDC_SYNC_STAGES(2), .DOUT_RESET_VALUE("0"), .ECC_MODE("no_ecc"), .FIFO_MEMORY_TYPE("distributed"), .FIFO_READ_LATENCY(0), .FIFO_WRITE_DEPTH(1 << AW),
        .FULL_RESET_VALUE(0), .PROG_EMPTY_THRESH(10), .PROG_FULL_THRESH(10), .RD_DATA_COUNT_WIDTH(CW), .READ_DATA_WIDTH(74), .READ_MODE("fwft"), .RELATED_CLOCKS(0),
        .SIM_ASSERT_CHK(0), .USE_ADV_FEATURES("0400"), .WAKEUP_TIME(0), .WRITE_DATA_WIDTH(74), .WR_DATA_COUNT_WIDTH(CW)) u_fifo (
        .sleep(1'b0), .rst(wrst), .wr_clk(wclk), .wr_en(wr_en), .din(w_ent), .full(f_full), .prog_full(), .wr_data_count(), .overflow(), .wr_rst_busy(wbusy),
        .almost_full(), .wr_ack(), .rd_clk(rclk), .rd_en(rd_en), .dout(head), .empty(f_empty), .prog_empty(), .rd_data_count(fill), .underflow(), .rd_rst_busy(rbusy),
        .almost_empty(), .data_valid(), .injectsbiterr(1'b0), .injectdbiterr(1'b0), .sbiterr(), .dbiterr());
    always_ff @(posedge wclk) begin
        if (w_v && !wbusy) begin
            if (f_full) n_ovf <= n_ovf + 32'd1;
            else n_wr <= n_wr + 32'd1;
        end
        if (clr_w) begin n_ovf <= '0; n_wr <= '0; end        // a clear wins over a count in the same clock
    end
    initial begin n_ovf = '0; n_wr = '0; end
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_lk (
        .src_clk(1'b0), .src_in(w_lock), .dest_clk(rclk), .dest_out(lock_s));

    // ---------------------------------------------------------------- read side
    logic            slot, in_frame, head_idle, head_frame, can_read, do_pop, do_del;
    logic [5:0]      pace;
    logic [1:0]      idle_run;
    assign can_read = !f_empty && !rbusy;
    assign slot = (pace != 6'd32);
    assign head_idle = head[73];
    // a start block (lane 0 or lane 4) or a data block leaves the stream inside a frame
    assign head_frame = (head[71:64] == 8'h00) || (head[71:64] == 8'h01 && head[7:0] == 8'hFB) || (head[71:64] == 8'h1F && head[39:32] == 8'hFB);
    assign do_pop = !rrst && can_read && lock_s && slot;                                  // a block is output
    logic            keep_ok;                                                             // enough pure idles output since the last frame (always true for MIN_KEEP = 0)
    if (MIN_KEEP == 0) begin : g_keep_none
        assign keep_ok = 1'b1;
    end else begin : g_keep_n
        assign keep_ok = (idle_run >= 2'(MIN_KEEP));
    end
    assign do_del = !rrst && can_read && lock_s && !slot && (fill > CW'(HI)) && !in_frame && keep_ok && head_idle;
    assign rd_en  = do_pop || do_del || (!rrst && can_read && !lock_s);                   // output, delete, or drain while the lock is low
    initial begin
        n_ins = '0; n_del = '0; n_stall = '0; n_out = '0; n_drain = '0; fill_min = '1; fill_max = '0; r_v = 1'b0; r_d = '0; r_c = '0; r_lock = 1'b0;
    end
    always_ff @(posedge rclk) begin
        r_v <= 1'b0;
        if (rrst) begin
            pace <= '0; in_frame <= 1'b0; idle_run <= '0; r_lock <= 1'b0; r_d <= '0; r_c <= '0;
            n_ins <= '0; n_del <= '0; n_stall <= '0; n_out <= '0; n_drain <= '0; fill_min <= '1; fill_max <= '0;
        end else begin
            pace <= (pace == 6'd32) ? 6'd0 : pace + 6'd1;
            r_lock <= lock_s;
            if (!lock_s) begin
                in_frame <= 1'b0; idle_run <= '0;
                if (can_read) n_drain <= n_drain + 32'd1;
            end else if (slot) begin
                if (!rbusy) begin
                    if (32'(fill) < fill_min) fill_min <= 32'(fill);
                    if (32'(fill) > fill_max) fill_max <= 32'(fill);
                end
                if (can_read) begin
                    r_v <= 1'b1; r_d <= head[63:0]; r_c <= head[71:64];
                    in_frame <= head_frame;
                    idle_run <= head_idle ? ((idle_run == 2'd3) ? 2'd3 : idle_run + 2'd1) : 2'd0;
                    n_out <= n_out + 32'd1;
                end else if (!in_frame && !rbusy) begin
                    r_v <= 1'b1; r_d <= 64'h0707070707070707; r_c <= 8'hFF;
                    idle_run <= (idle_run == 2'd3) ? 2'd3 : idle_run + 2'd1;
                    n_ins <= n_ins + 32'd1; n_out <= n_out + 32'd1;
                end else if (!rbusy) n_stall <= n_stall + 32'd1;
            end else if (do_del) n_del <= n_del + 32'd1;
            if (clr_r) begin n_ins <= '0; n_del <= '0; n_stall <= '0; n_out <= '0; n_drain <= '0; fill_min <= '1; fill_max <= '0; end     // a clear wins over a count in the same clock
        end
    end
endmodule
