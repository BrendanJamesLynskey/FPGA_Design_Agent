// rx_path_legacy.sv (build rm_gp_ml, brief 113: a copy of rtl/rx_path_legacy.sv whose trade64 has the ML stage's ports tied off: this path has no ML stage; the line that differs is marked 113)
// rx_path_legacy.sv: the receive path of brief 96 / 97C, as it was on main 6909e43f, kept for b96_core's RATE_MATCH = 0 (the default since the owner's decision of
// 2026-11-19: brief 96C's elastic buffer is a build option). Everything below the module line is the 6909e43f rx_path.sv, byte for byte, except the module name
// and the pcs_rx instance's new (unused) x_os port. It is not part of the rate-matched design (rx_path.sv).
// Original header:
// rx_path.sv: the receive side of brief 96's 10G design, in the receive user-clock domain (RXUSRCLK2, the clock the GT recovers from the
// line): the GT's 64-bit RXDATA -> pcs_rx -> mac64_rx -> trade64, the receive counters and the events sent to the transmit domain.
// The counters are cleared only by `clr_p` (so they survive a link restart; the order number is also restarted by `seq_p`, brief 97C); the PCS and MAC state is held in reset by `rst`.
module rx_path_legacy #(
    parameter int NRXW = 18
) (
    input  logic        clk,                 // RXUSRCLK2
    input  logic        rst,                 // hold while the GT's receive side is not up
    input  logic [b96_pkg::CFGW-1:0] cfg,
    input  logic        clr_p,
    input  logic        seq_p,               // restart the order number (a restart of either side; from the register domain)
    input  logic [63:0] gt_d,
    output logic        fire,
    output logic [15:0] o_inst,
    output logic [31:0] o_price, o_qty, o_seq,
    output logic        verdict_v, verdict_bad,
    output logic [31:0] verdict_seq,
    output logic        rx_sop, cls_feed, cls_order, cls_probe,
    output logic        lock,
    output logic [32 * NRXW - 1:0] rx_vec
);
    logic [47:0] my_mac, venue_mac;
    logic [31:0] my_ip, venue_ip, thr, qty;
    logic [15:0] sport, port_feed, port_order, port_probe;
    logic        arm, kill, trade_en;
    logic [1:0]  gen_kind;
    logic [15:0] gen_len, gen_inst;
    logic [31:0] gen_price, gen_interval, gen_count;
    assign {gen_count, gen_interval, gen_price, gen_inst, gen_len, gen_kind, trade_en, kill, arm, qty, thr, port_probe, port_order,
            port_feed, sport, venue_ip, my_ip, venue_mac, my_mac} = cfg;
    logic        x_v;
    logic [63:0] x_d;
    logic [7:0]  x_c;
    logic        ev_sh_err, ev_type_err, ev_os, ev_slip, ev_loss, ev_lock;
    pcs_rx u_pr (.clk, .rst, .gt_d, .x_v, .x_d, .x_c, .x_os(), .lock, .ev_sh_err, .ev_type_err, .ev_os, .ev_slip, .ev_loss, .ev_lock);
    logic        m_v, m_sof, m_end, m_fcs_ok, m_err;
    logic [63:0] m_d;
    logic [3:0]  m_nb;
    logic [15:0] m_len;
    mac64_rx u_mr (.clk, .rst, .lock_i(lock), .x_v, .x_d, .x_c, .m_v, .m_d, .m_sof, .m_nb, .m_end, .m_fcs_ok, .m_len, .m_err, .rx_sop);
    logic [31:0] n_frames, n_good, n_bad, n_fired, n_blocked, n_toolong, n_order_ok, n_order_bad;
    trade64 u_td (.ml_en_veto(1'b0), .ml_inst(16'd0), .ml_st_rst(1'b0), .ml_vec(), .clk, .rst, .clr(clr_p), .seq_clr(seq_p), .m_v, .m_d, .m_sof, .m_end, .m_fcs_ok, .m_len, .m_err, .my_mac, .venue_mac, .port_feed, .port_order, .port_probe,
        .thr, .qty, .arm, .kill, .trade_en, .fire, .o_inst, .o_price, .o_qty, .o_seq, .cls_feed, .cls_order, .cls_probe,
        .verdict_v, .verdict_bad, .verdict_seq, .n_frames, .n_good, .n_bad, .n_fired, .n_blocked, .n_toolong, .n_order_ok, .n_order_bad);
    // counters
    logic [31:0] c_slip, c_loss, c_lock, c_sh, c_type, c_os, c_err, lock_clk, last_len;
    logic        locked_once;
    initial begin c_slip = '0; c_loss = '0; c_lock = '0; c_sh = '0; c_type = '0; c_os = '0; c_err = '0; lock_clk = '0; last_len = '0; locked_once = 1'b0; end
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
        if (m_err) c_err <= c_err + 32'd1;
        if (m_end) last_len <= {16'd0, m_len};
        if (clr_p) begin c_slip <= '0; c_loss <= '0; c_lock <= '0; c_sh <= '0; c_type <= '0; c_os <= '0; c_err <= '0; end
    end
    logic [31:0] rw [NRXW];
    always_comb begin
        rw[0] = {31'd0, lock}; rw[1] = c_slip; rw[2] = c_loss; rw[3] = c_lock; rw[4] = c_sh; rw[5] = c_type; rw[6] = c_os;
        rw[7] = n_frames; rw[8] = n_good; rw[9] = n_bad; rw[10] = c_err; rw[11] = n_fired; rw[12] = n_blocked; rw[13] = n_toolong;
        rw[14] = last_len; rw[15] = lock_clk; rw[16] = n_order_ok; rw[17] = n_order_bad;
    end
    always_comb for (int i = 0; i < NRXW; i++) rx_vec[32 * i +: 32] = rw[i];
    logic _unused;
    assign _unused = &{1'b0, my_ip, venue_ip, sport, gen_kind, gen_len, gen_inst, gen_price, gen_interval, gen_count, m_nb};
endmodule
