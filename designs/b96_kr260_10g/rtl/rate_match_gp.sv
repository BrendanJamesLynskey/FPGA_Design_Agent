// rate_match_gp.sv: brief 96E's low-latency elastic buffer. Same ports and the same idle insert/delete policy as rate_match.sv (brief 96C), but the crossing is our own
// gray-pointer asynchronous-FIFO structure instead of AMD's xpm_fifo_async, which cuts the buffer's latency from 9 to 13 clocks (the macro, measured in xsim) to about 4 to 5 (docs/design.md section 11).
//
// Why the macro is slow: its `empty` flag and read data count come from a pointer that crosses by xpm_cdc_gray (2 flops) and is then registered again, and `empty` is itself a register;
// first-word-fall-through adds a registered output stage. Here the pointer crossing is the bare minimum AMD allows for a safe multi-bit pointer (UG974, xpm_cdc_gray: DEST_SYNC_FF = 2).
//
//   storage: DEPTH blocks in flip-flops in the write clock. An entry is written once and then held until the reader has released it: the writer sees the read pointer (old, so conservative)
//     and never overwrites an entry the reader has not passed.
//   write pointer: binary count in the write clock, crossing by xpm_cdc_gray (a gray register in the write clock = one write clock after the entry was loaded, then DEST_SYNC_FF flops in the read clock).
//   ENT_SYNC = 1 (the default, what rm_gp builds): every entry is also copied bit for bit through its own two-flop ASYNC_REG synchroniser (xpm_cdc_array_single) into the read clock, continuously, and the
//     write pointer crosses with THREE flops. A data bit that goes metastable in its first flop resolves within a clock, so after its second flop it has settled; the pointer's third flop makes the pointer
//     arrive at least one clock after the data copies have settled, whatever the routing skew between the bits is (as long as it is under a clock). The reader selects among the settled copies with its own read pointer.
//     This costs one clock against ENT_SYNC = 0 and passes report_cdc (the data bits are CDC-3, synchronised with ASYNC_REG).
//   ENT_SYNC = 0 (rm_gp_direct, kept as evidence): the standard asynchronous FIFO read, the reader selects the entry flops directly with its read pointer and registers the result in the read clock;
//     bounded by rate_match_gp.xdc (set_max_delay -datapath_only, one read-clock period). It is faster by one clock and safe by the pointer rule (the pointer admits an entry about 2 read clocks after it
//     changed), but report_cdc cannot classify a write-clock flop (or RAM) read through logic in the read clock: 38 CDC-1 Critical rows, so the flow's cdc_no_critical gate fails (docs/design.md section 11).
//   read pointer: binary in the read clock, crosses to the write clock by xpm_cdc_gray; the writer stops when DEPTH blocks are outstanding as it sees them (conservative: its view is old).
//   read side policy (identical to rate_match.sv except the fill the policy reads is exact in the read clock's view: blocks whose pointer has crossed):
//     slot, a block visible       -> pop and output it;     slot, none, not in a frame -> insert one idle block;     slot, none, inside a frame -> output nothing for one clock (stall);
//     pause clock, visible fill > HI, not in a frame, head a pure idle -> delete it.   HI defaults to 1 here (one block of fill; rate_match.sv's is 4: its fill count lags the writer, ours does not).
//   While the synchronised block lock is low the reader discards the buffer's content, one block a clock, and outputs nothing.
//   No reset of the pointers: they are never reset, so a reset of one side can never leave them inconsistent. Reset of the write side only stops writing (wrst); the reader drains the buffer
//   while the lock is low. Counters and the reader's state reset with rrst as in rate_match.sv.
// Registered output: r_v/r_d/r_c/r_lock (as rate_match.sv).
module rate_match_gp #(
    parameter int AW       = 4,     // 2**AW blocks (16: the writer's view of the read pointer is about 4 clocks old and the reader's of the write pointer about 4, so about 8 blocks are outstanding in steady state)
    parameter int HI       = 1,     // delete idles while the visible fill is above this
    parameter bit ENT_SYNC = 1'b1,  // 1: every entry is copied through its own 2-flop synchroniser and the write pointer crosses with 3 flops (passes report_cdc); 0: the reader reads the entry flops directly (set_max_delay in rate_match_gp.xdc; report_cdc flags it CDC-1 Critical, see docs/design.md section 11)
    parameter int MIN_KEEP = 0      // as rate_match.sv: delete only after this many consecutive pure idle blocks were output (0 or 1 or 2 or 3)
) (
    input  logic        wclk,
    input  logic        wrst,       // write-domain reset (receive side down): stops writing
    input  logic        w_v,        // a decoded block this clock
    input  logic [63:0] w_d,
    input  logic [7:0]  w_c,
    input  logic        w_os,       // the block was an ordered set (shown by the decoder as idles)
    input  logic        w_lock,     // PCS block lock (write domain)
    input  logic        clr_w,      // clear the write-side counters (write domain pulse)
    output logic [31:0] n_ovf = '0, n_wr = '0,
    input  logic        rclk,
    input  logic        rrst,
    input  logic        clr_r,      // clear the read-side counters (read domain pulse)
    output logic        r_v = 1'b0,
    output logic [63:0] r_d = '0,
    output logic [7:0]  r_c = '0,
    output logic        r_lock = 1'b0,
    output logic [31:0] n_ins = '0, n_del = '0, n_stall = '0, n_out = '0, n_drain = '0, fill_min = '1, fill_max = '0
);
    localparam int DEPTH = 1 << AW;
    localparam int CW    = AW + 1;                       // pointers count to 2*DEPTH
    localparam int EW    = 74;                           // {pure idle, ordered set, c[7:0], d[63:0]}
    logic [EW-1:0] w_ent;
    assign w_ent = {(w_c == 8'hFF) && (w_d == 64'h0707070707070707) && !w_os, w_os, w_c, w_d};

    // ---------------------------------------------------------------- write side (wclk)
    logic [EW-1:0]  ent [DEPTH];
    logic [CW-1:0]  wbin = '0;                           // written entries (binary, counts mod 2*DEPTH); declared with its power-up value (no initial block: xsim refuses those beside always_ff)
    logic [CW-1:0]  rbin_w;                              // the read pointer as the write side sees it (old)
    logic           f_full, wr_en;
    assign f_full = ((wbin - rbin_w) & {CW{1'b1}}) >= CW'(DEPTH);
    assign wr_en  = w_v && !f_full && !wrst;
    always_ff @(posedge wclk) begin
        if (wr_en) begin
            ent[wbin[AW-1:0]] <= w_ent;
            wbin <= wbin + CW'(1);
        end
    end
    always_ff @(posedge wclk) begin
        if (w_v && !wrst) begin
            if (f_full) n_ovf <= n_ovf + 32'd1;
            else n_wr <= n_wr + 32'd1;
        end
        if (clr_w) begin n_ovf <= '0; n_wr <= '0; end        // a clear wins over a count in the same clock
    end

    // ---------------------------------------------------------------- the crossings
    logic [CW-1:0] wbin_r;                               // the write pointer in the read clock
    xpm_cdc_gray #(.DEST_SYNC_FF(ENT_SYNC ? 3 : 2), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .SIM_ASSERT_CHK(1), .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(CW)) u_wp (
        .src_clk(wclk), .src_in_bin(wbin), .dest_clk(rclk), .dest_out_bin(wbin_r));
    logic [CW-1:0] rbin = '0;
    xpm_cdc_gray #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .SIM_ASSERT_CHK(1), .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(CW)) u_rp (
        .src_clk(rclk), .src_in_bin(rbin), .dest_clk(wclk), .dest_out_bin(rbin_w));
    logic [EW-1:0] ent_r [DEPTH];                        // ENT_SYNC = 1: every entry copied into the read clock (stable long before the write pointer admits it)
    for (genvar gi = 0; gi < DEPTH; gi++) begin : g_ent
        if (ENT_SYNC) begin : s
            xpm_cdc_array_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(0), .WIDTH(EW)) u_e (
                .src_clk(wclk), .src_in(ent[gi]), .dest_clk(rclk), .dest_out(ent_r[gi]));
        end else begin : d
            assign ent_r[gi] = ent[gi];
        end
    end
    logic lock_s;
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(0)) u_lk (
        .src_clk(1'b0), .src_in(w_lock), .dest_clk(rclk), .dest_out(lock_s));

    // ---------------------------------------------------------------- read side (rclk)
    logic [EW-1:0]   head;
    logic [CW-1:0]   fill;
    logic            slot, in_frame, head_idle, head_frame, can_read, do_pop, do_del, keep_ok;
    logic [5:0]      pace;
    logic [1:0]      idle_run;
    assign head      = ent_r[rbin[AW-1:0]];          // ENT_SYNC = 0: the write clock's entry flops directly (see the header: bounded by rate_match_gp.xdc)
    assign fill      = (wbin_r - rbin) & {CW{1'b1}};     // blocks whose write pointer has crossed and that are not yet read
    assign can_read  = (fill != '0);
    assign slot      = (pace != 6'd32);
    assign head_idle = head[73];
    assign head_frame = (head[71:64] == 8'h00) || (head[71:64] == 8'h01 && head[7:0] == 8'hFB) || (head[71:64] == 8'h1F && head[39:32] == 8'hFB);
    assign do_pop = !rrst && can_read && lock_s && slot;
    if (MIN_KEEP == 0) begin : g_keep_none
        assign keep_ok = 1'b1;
    end else begin : g_keep_n
        assign keep_ok = (idle_run >= 2'(MIN_KEEP));
    end
    assign do_del = !rrst && can_read && lock_s && !slot && (fill > CW'(HI)) && !in_frame && keep_ok && head_idle;
    logic rd_en;
    assign rd_en  = do_pop || do_del || (!rrst && can_read && !lock_s);                   // output, delete, or drain while the lock is low
    always_ff @(posedge rclk) begin
        if (rd_en) rbin <= rbin + CW'(1);
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
                if (32'(fill) < fill_min) fill_min <= 32'(fill);
                if (32'(fill) > fill_max) fill_max <= 32'(fill);
                if (can_read) begin
                    r_v <= 1'b1; r_d <= head[63:0]; r_c <= head[71:64];
                    in_frame <= head_frame;
                    idle_run <= head_idle ? ((idle_run == 2'd3) ? 2'd3 : idle_run + 2'd1) : 2'd0;
                    n_out <= n_out + 32'd1;
                end else if (!in_frame) begin
                    r_v <= 1'b1; r_d <= 64'h0707070707070707; r_c <= 8'hFF;
                    idle_run <= (idle_run == 2'd3) ? 2'd3 : idle_run + 2'd1;
                    n_ins <= n_ins + 32'd1; n_out <= n_out + 32'd1;
                end else n_stall <= n_stall + 32'd1;
            end else if (do_del) n_del <= n_del + 32'd1;
            if (clr_r) begin n_ins <= '0; n_del <= '0; n_stall <= '0; n_out <= '0; n_drain <= '0; fill_min <= '1; fill_max <= '0; end     // a clear wins over a count in the same clock
        end
    end
endmodule
