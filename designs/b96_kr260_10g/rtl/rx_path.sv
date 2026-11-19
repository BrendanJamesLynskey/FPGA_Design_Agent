// rx_path.sv: the receive side of brief 96's 10G design, in TWO clock domains since brief 96C:
//   receive user clock (RXUSRCLK2, recovered from the line: the partner's frequency): the GT's 64-bit RXDATA -> pcs_rx -> the write side of
//     rate_match, the PCS counters and a free-running clock counter (the frequency counter's receive half);
//   core clock (TXUSRCLK2, ours): the read side of rate_match (which keeps the two clocks' difference of up to +-100 ppm from ever losing or
//     corrupting a frame: it inserts or deletes idle blocks between frames) -> mac64_rx -> trade64, the receive-side counters and the events sent to the transmit logic
//     (same domain: no crossing).
// The PCS counters are cleared only by `clr_w`, the MAC and rate-match counters by `clr_c` (so they survive a link restart; the order number is
// also restarted by `seq_c`, brief 97C); the PCS and MAC state is held in reset by `rst` / `rst_c`.
// The status words RXV0..RXV28 (docs/register_map.md) come out as two packed vectors, one per domain (b96_pkg: RXV_OWN_W says which is which).
module rx_path #(
    parameter bit RM_DIRECT = 1'b0,    // brief 96E: with RM_OWN, 1 = rate_match_gp's ENT_SYNC = 0
    parameter bit RM_OWN = 1'b0     // brief 96E: 1 = rate_match_gp (own gray-pointer buffer, about 5 clocks), 0 = rate_match (AMD's xpm_fifo_async, 9 to 13 clocks)
) (
    input  logic        clk,                 // RXUSRCLK2
    input  logic        rst,                 // hold while the GT's receive side is not up
    input  logic        clk_c,               // core clock (TXUSRCLK2)
    input  logic        rst_c,               // hold while the GT's transmit side is not up
    input  logic [b96_pkg::CFGW-1:0] cfg,    // configuration, in the core clock domain
    input  logic        clr_w,               // clear the PCS counters (pulse, receive domain)
    input  logic        clr_c,               // clear the MAC, trade and rate-match counters (pulse, core domain)
    input  logic        seq_c,               // restart the order number (pulse, core domain; a restart of either side, from the register domain)
    input  logic [63:0] gt_d,
    // core domain
    output logic        fire,
    output logic [15:0] o_inst,
    output logic [31:0] o_price, o_qty, o_seq,
    output logic        verdict_v, verdict_bad,
    output logic [31:0] verdict_seq,
    output logic        rx_sop, cls_feed, cls_order, cls_probe,
    // receive domain
    output logic        lock,
    output logic [32 * b96_pkg::NRXV_W - 1:0] rx_vec_w,
    output logic [32 * b96_pkg::NRXV_C - 1:0] rx_vec_c
);
    import b96_pkg::*;
    logic [47:0] my_mac, venue_mac;
    logic [31:0] my_ip, venue_ip, thr, qty;
    logic [15:0] sport, port_feed, port_order, port_probe;
    logic        arm, kill, trade_en;
    logic [1:0]  gen_kind;
    logic [15:0] gen_len, gen_inst;
    logic [31:0] gen_price, gen_interval, gen_count;
    assign {gen_count, gen_interval, gen_price, gen_inst, gen_len, gen_kind, trade_en, kill, arm, qty, thr, port_probe, port_order,
            port_feed, sport, venue_ip, my_ip, venue_mac, my_mac} = cfg;
    // ---------------------------------------------------------------- receive clock: PCS and the elastic buffer's write side
    logic        x_v, x_os;
    logic [63:0] x_d;
    logic [7:0]  x_c;
    logic        ev_sh_err, ev_type_err, ev_os, ev_slip, ev_loss, ev_lock;
    pcs_rx u_pr (.clk, .rst, .gt_d, .x_v, .x_d, .x_c, .x_os, .lock, .ev_sh_err, .ev_type_err, .ev_os, .ev_slip, .ev_loss, .ev_lock);
    // ---------------------------------------------------------------- elastic buffer (rate matching)
    logic        y_v, y_lock;
    logic [63:0] y_d;
    logic [7:0]  y_c;
    logic [31:0] rm_ovf, rm_wr, rm_ins, rm_del, rm_stall, rm_out, rm_drain, rm_fmin, rm_fmax;
    if (RM_OWN) begin : g_own
        rate_match_gp #(.ENT_SYNC(!RM_DIRECT)) u_rm (.wclk(clk), .wrst(rst), .w_v(x_v), .w_d(x_d), .w_c(x_c), .w_os(x_os), .w_lock(lock), .clr_w, .n_ovf(rm_ovf), .n_wr(rm_wr),
            .rclk(clk_c), .rrst(rst_c), .clr_r(clr_c), .r_v(y_v), .r_d(y_d), .r_c(y_c), .r_lock(y_lock),
            .n_ins(rm_ins), .n_del(rm_del), .n_stall(rm_stall), .n_out(rm_out), .n_drain(rm_drain), .fill_min(rm_fmin), .fill_max(rm_fmax));
    end else begin : g_xpm
        rate_match u_rm (.wclk(clk), .wrst(rst), .w_v(x_v), .w_d(x_d), .w_c(x_c), .w_os(x_os), .w_lock(lock), .clr_w, .n_ovf(rm_ovf), .n_wr(rm_wr),
            .rclk(clk_c), .rrst(rst_c), .clr_r(clr_c), .r_v(y_v), .r_d(y_d), .r_c(y_c), .r_lock(y_lock),
            .n_ins(rm_ins), .n_del(rm_del), .n_stall(rm_stall), .n_out(rm_out), .n_drain(rm_drain), .fill_min(rm_fmin), .fill_max(rm_fmax));
    end
    // ---------------------------------------------------------------- core clock: MAC and the trading path
    logic        m_v, m_sof, m_end, m_fcs_ok, m_err;
    logic [63:0] m_d;
    logic [3:0]  m_nb;
    logic [15:0] m_len;
    mac64_rx u_mr (.clk(clk_c), .rst(rst_c), .lock_i(y_lock), .x_v(y_v), .x_d(y_d), .x_c(y_c), .m_v, .m_d, .m_sof, .m_nb, .m_end, .m_fcs_ok, .m_len, .m_err, .rx_sop);
    logic [31:0] n_frames, n_good, n_bad, n_fired, n_blocked, n_toolong, n_order_ok, n_order_bad;
    trade64 u_td (.clk(clk_c), .rst(rst_c), .clr(clr_c), .seq_clr(seq_c), .m_v, .m_d, .m_sof, .m_end, .m_fcs_ok, .m_len, .m_err, .my_mac, .venue_mac, .port_feed, .port_order, .port_probe,
        .thr, .qty, .arm, .kill, .trade_en, .fire, .o_inst, .o_price, .o_qty, .o_seq, .cls_feed, .cls_order, .cls_probe,
        .verdict_v, .verdict_bad, .verdict_seq, .n_frames, .n_good, .n_bad, .n_fired, .n_blocked, .n_toolong, .n_order_ok, .n_order_bad);
    // ---------------------------------------------------------------- frequency counter (brief 96C): the receive clock's cycles in a window of 2**24 core clocks
    // A free-running count in the receive domain crosses as a gray code; the core domain samples it every 2**24 core clocks (104 ms) and keeps the difference
    // of the last two samples: ppm = (delta - 2**24) / 2**24 * 1e6 (positive: the receive clock is faster than the core clock). The two samples are each
    // a few clocks late, by the same amount, so the error of one difference is about 2 counts in 16.8 million (0.1 ppm).
    logic [31:0] rcnt, rcnt_s, rcnt_prev, f_delta, f_win;
    logic [23:0] tcnt;
    logic        primed;          // the first window end after a core restart only loads the previous sample (a difference to a stale sample would be garbage)
    initial begin rcnt = '0; rcnt_prev = '0; f_delta = '0; f_win = '0; tcnt = '0; primed = 1'b0; end
    always_ff @(posedge clk) rcnt <= rcnt + 32'd1;
    xpm_cdc_gray #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .SIM_ASSERT_CHK(0), .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(32)) u_fc (
        .src_clk(clk), .src_in_bin(rcnt), .dest_clk(clk_c), .dest_out_bin(rcnt_s));
    always_ff @(posedge clk_c) begin
        if (rst_c) begin tcnt <= '0; f_win <= '0; f_delta <= '0; primed <= 1'b0; end
        else begin
            tcnt <= tcnt + 24'd1;
            if (tcnt == 24'hFFFFFF) begin
                rcnt_prev <= rcnt_s; primed <= 1'b1;
                if (primed) begin f_delta <= rcnt_s - rcnt_prev; f_win <= f_win + 32'd1; end
            end
        end
    end
    // ---------------------------------------------------------------- PCS counters (receive clock)
    logic [31:0] c_slip, c_loss, c_lock, c_sh, c_type, c_os, lock_clk;
    logic        locked_once;
    initial begin c_slip = '0; c_loss = '0; c_lock = '0; c_sh = '0; c_type = '0; c_os = '0; lock_clk = '0; locked_once = 1'b0; end
    always_ff @(posedge clk) begin
        if (rst) begin locked_once <= 1'b0; lock_clk <= '0; end
        else begin
            if (!locked_once) lock_clk <= lock_clk + 32'd1;
            if (ev_lock) locked_once <= 1'b1;
        end
        if (ev_slip) c_slip <= c_slip + 32'd1;
        if (ev_loss) c_loss <= c_loss + 32'd1;
        if (ev_lock) c_lock <= c_lock + 32'd1;
        if (ev_sh_err) c_sh <= c_sh + 32'd1;
        if (ev_type_err) c_type <= c_type + 32'd1;
        if (ev_os) c_os <= c_os + 32'd1;
        if (clr_w) begin c_slip <= '0; c_loss <= '0; c_lock <= '0; c_sh <= '0; c_type <= '0; c_os <= '0; end
    end
    // ---------------------------------------------------------------- core-clock counters
    logic [31:0] c_err, last_len;
    initial begin c_err = '0; last_len = '0; end
    always_ff @(posedge clk_c) begin
        if (m_err) c_err <= c_err + 32'd1;
        if (m_end) last_len <= {16'd0, m_len};
        if (clr_c) c_err <= '0;
    end
    logic [31:0] rw [NRXW];
    always_comb begin
        rw[0] = {31'd0, lock}; rw[1] = c_slip; rw[2] = c_loss; rw[3] = c_lock; rw[4] = c_sh; rw[5] = c_type; rw[6] = c_os;
        rw[7] = n_frames; rw[8] = n_good; rw[9] = n_bad; rw[10] = c_err; rw[11] = n_fired; rw[12] = n_blocked; rw[13] = n_toolong;
        rw[14] = last_len; rw[15] = lock_clk; rw[16] = n_order_ok; rw[17] = n_order_bad;
        rw[18] = rm_wr; rw[19] = rm_ovf; rw[20] = rm_ins; rw[21] = rm_del; rw[22] = rm_stall; rw[23] = rm_out; rw[24] = rm_drain;
        rw[25] = rm_fmin; rw[26] = rm_fmax; rw[27] = f_delta; rw[28] = f_win;
    end
    for (genvar gi = 0; gi < NRXW; gi++) begin : g_pack
        if (RXV_OWN_W[gi]) begin : w
            assign rx_vec_w[32 * rxv_pos(1'b1, gi) +: 32] = rw[gi];
        end else begin : c
            assign rx_vec_c[32 * rxv_pos(1'b0, gi) +: 32] = rw[gi];
        end
    end
    logic _unused;
    assign _unused = &{1'b0, my_ip, venue_ip, sport, gen_kind, gen_len, gen_inst, gen_price, gen_interval, gen_count, m_nb, rcnt_s[0]};
endmodule
