// tx_path.sv (variant rm_gp_itch of brief 127: the MAC is fed through tx_mux (frame_src, the replay source and the ITCH order stream); the counters of frame_src's frames count only its own
// frames; everything else is the base file): the transmit side of brief 96's 10G design, all in the transmit user-clock domain (TXUSRCLK2, 161.1328125 MHz):
// frame_src -> mac64_tx -> pcs_tx -> the GT's 64-bit TXDATA, with the frame generator (host-started feed, probe and test frames), the
// order path (a pulse from the receive domain starts the order frame, with the live fields on a quasi-static bus), the timestamps of
// the loop measurement and the transmit counters.
//
// Timestamps: one free-running 32-bit counter `ts` in this domain. TX start events are stamped here directly (the clock of the MAC's
// start strobe). Since brief 96C the receive MAC and the trading decision run in this same clock (behind the elastic buffer rate_match), so the RX events
// (rx_sop_p and the class pulses) and the go message arrive as ordinary same-clock signals, not through a crossing: an RX stamp has no crossing latency or phase term
// (it includes the elastic buffer's latency, design.md section 9). The comments below that say "from the receive domain" mean the receive path's logic.
module tx_path #(
    parameter int NTXW = 26
) (
    input  logic        clk,                 // TXUSRCLK2
    input  logic        rst,                 // hold while the GT's transmit side is not up
    input  logic [b96_pkg::CFGW-1:0] cfg,    // configuration (layout in b96_core)
    input  logic        clr_p,               // clear counters (pulse)
    input  logic        gen_go_p,            // start the generator's run (pulse)
    input  logic        seq_p,               // restart the order count (pulse): a restart of either side, from the register domain (97C)
    // from the receive domain
    input  logic        go_p,                // an order is wanted
    input  logic [15:0] go_inst,
    input  logic [31:0] go_price, go_qty, go_seq,
    input  logic        verdict_v, verdict_bad,
    input  logic [31:0] verdict_seq,
    input  logic        rx_sop_p, rx_feed_p, rx_order_p, rx_probe_p,
    // to the GT
    output logic [63:0] gt_d,
    output logic [32 * NTXW - 1:0] tx_vec,
    // brief 127: the ITCH path's order stream, the replay commands and the observations
    output logic [31:0] ts_o,
    input  logic        i_o_v,
    input  logic [63:0] i_o_d,
    input  logic        i_o_sof, i_o_eof,
    input  logic [7:0]  i_o_keep,
    input  logic        i_o_poison, i_o_unres, i_fcs_poison,
    input  logic        i_rp_start, i_rp_stop, i_wr_we,
    input  logic [15:0] i_rp_loops,
    input  logic [7:0]  i_wr_addr,
    input  logic [63:0] i_wr_data,
    output logic        ord_start, ord_drop, ord_end, ord_end_seg, ord_end_unres, ord_end_fcs, ord_end_ofl, ord_sop, ord_busy,
    output logic [31:0] rp_frames, rp_err, n_ofl,
    output logic        rp_busy
);
    import b96_pkg::*;
    // ---------------------------------------------------------------- configuration
    logic [47:0] my_mac, venue_mac;
    logic [31:0] my_ip, venue_ip, thr, qty;
    logic [15:0] sport, port_feed, port_order, port_probe;
    logic        arm, kill, trade_en;
    logic [1:0]  gen_kind;
    logic [15:0] gen_len, gen_inst;
    logic [31:0] gen_price, gen_interval, gen_count;
    assign {gen_count, gen_interval, gen_price, gen_inst, gen_len, gen_kind, trade_en, kill, arm, qty, thr, port_probe, port_order,
            port_feed, sport, venue_ip, my_ip, venue_mac, my_mac} = cfg;

    // ---------------------------------------------------------------- time
    logic [31:0] ts;
    always_ff @(posedge clk) ts <= rst ? 32'd0 : ts + 32'd1;
    assign ts_o = ts;

    // ---------------------------------------------------------------- frame source and MAC
    logic        fs_start, fs_busy, s_valid, s_last, s_ready, adv, sop, eop, underrun, poison;
    logic [1:0]  fs_kind;
    logic [15:0] fs_len;
    logic [63:0] s_data;
    logic [2:0]  s_nb1;
    logic        stale_p;
    logic [31:0] seq_seen;
    logic [31:0] stale, go_cnt, b_price, b_qty, b_seq, want_seq;
    logic [15:0] b_inst;
    logic [63:0] x_d;
    logic [7:0]  x_c;
    logic [1:0]  cur_kind;
    logic        order_pend;
    // live fields: the order's fields from the decision (same clock since 96C), the generator's own for the other kinds
    logic [31:0] gen_seq;
    logic [1:0]  bus_kind;
    logic [31:0] go_seq_l;      // the order number latched at the go pulse
    assign bus_kind = fs_start ? fs_kind : cur_kind;
    assign b_inst  = (bus_kind == 2'd0) ? go_inst : gen_inst;
    assign b_price = (bus_kind == 2'd0) ? go_price : gen_price;
    assign b_qty   = (bus_kind == 2'd0) ? go_qty : 32'd1;
    assign b_seq   = (bus_kind == 2'd0) ? go_seq : gen_seq;
    assign want_seq = (bus_kind == 2'd0) ? go_cnt : gen_seq;
    // orders go from us to the venue; the generator's frames come from the "venue" to us (they loop back through the optics or a NIC)
    logic is_order;
    assign is_order = (bus_kind == 2'd0);
    frame_src u_fs (.clk, .rst, .start(fs_start), .clr(clr_p), .kind(fs_kind), .len(fs_len), .dst_mac(is_order ? venue_mac : my_mac),
        .src_mac(is_order ? my_mac : venue_mac), .src_ip(is_order ? my_ip : venue_ip),
        .dst_ip(is_order ? venue_ip : my_ip), .sport(is_order ? sport : port_order), .dport_order(port_order), .dport_feed(port_feed), .dport_probe(port_probe),
        .b_inst, .b_price, .b_qty, .b_seq, .want_seq, .busy(fs_busy), .stale, .stale_p, .seq_seen, .s_valid, .s_data, .s_last, .s_nb1, .s_ready);
    // poison: the order's FCS is made wrong when the frame that caused it turned out bad (verdict arrives long before the last word:
    // the trading path never acts on frames long enough for it not to)
    logic verdict_good;
    assign verdict_good = verdict_v && !verdict_bad && (verdict_seq == go_seq_l);
    assign poison = (cur_kind == 2'd0) && !verdict_good;      // fail closed: unless the verdict for THIS order is known good
    // brief 127: three frame sources share the MAC; s_* above are frame_src's (source A), m_* go to the MAC
    logic        m_valid, m_last, m_poison, m_ready, own_a;
    logic [63:0] m_data;
    logic [2:0]  m_nb1;
    tx_mux u_mx (.clk, .rst, .s_valid(m_valid), .s_data(m_data), .s_last(m_last), .s_nb1(m_nb1), .s_poison(m_poison), .s_ready(m_ready), .mac_sop(sop),
        .a_valid(s_valid), .a_data(s_data), .a_last(s_last), .a_nb1(s_nb1), .a_poison(poison), .a_ready(s_ready),
        .o_v(i_o_v), .o_d(i_o_d), .o_sof(i_o_sof), .o_eof(i_o_eof), .o_keep(i_o_keep), .o_poison(i_o_poison), .o_unres(i_o_unres), .fcs_poison(i_fcs_poison),
        .ord_start, .ord_drop, .ord_end, .ord_end_seg, .ord_end_unres, .ord_end_fcs, .ord_end_ofl, .ord_sop, .ord_busy, .own_a,
        .rp_start(i_rp_start), .rp_stop(i_rp_stop), .rp_loops(i_rp_loops), .wr_we(i_wr_we), .wr_addr(i_wr_addr), .wr_data(i_wr_data), .rp_frames, .rp_err, .rp_busy, .n_ofl);
    mac64_tx u_mt (.clk, .rst, .adv, .s_valid(m_valid), .s_data(m_data), .s_last(m_last), .s_nb1(m_nb1), .s_poison(m_poison), .s_ready(m_ready), .x_d, .x_c, .sop, .eop, .underrun);
    pcs_tx   u_pt (.clk, .rst, .x_d, .x_c, .adv, .gt_d);

    // ---------------------------------------------------------------- what to send next
    logic [31:0] gen_left, gen_wait;
    logic        gen_due;
    assign gen_due = (gen_left != 32'd0) && (gen_wait == 32'd0);
    assign fs_start = !fs_busy && !s_valid && (go_p ? 1'b1 : gen_due);
    assign fs_kind  = go_p ? 2'd0 : gen_kind;
    assign fs_len   = go_p ? 16'd66 : gen_len;
    logic [31:0] n_sent_order, n_sent_feed, n_sent_probe, n_sent_test, n_poisoned, n_dropped, n_underrun, n_late;
    logic [31:0] t_tx_feed, t_tx_probe, t_tx_order, t_rx_sop, t_rx_feed, t_rx_probe, t_rx_order;
    logic [31:0] e_last, e_min, e_max, e_cnt, l_last, l_min, l_max, l_cnt, d_last;
    logic        start_q;
    always_ff @(posedge clk) begin
        if (rst) begin
            gen_left <= '0; gen_wait <= '0; gen_seq <= 32'd0; go_cnt <= '0; go_seq_l <= '0; cur_kind <= '0; order_pend <= 1'b0;
            n_sent_order <= '0; n_sent_feed <= '0; n_sent_probe <= '0; n_sent_test <= '0; n_poisoned <= '0; n_dropped <= '0;
            n_underrun <= '0; n_late <= '0;
            t_tx_feed <= '0; t_tx_probe <= '0; t_tx_order <= '0; t_rx_sop <= '0; t_rx_feed <= '0; t_rx_probe <= '0; t_rx_order <= '0;
            e_last <= '0; e_min <= '1; e_max <= '0; e_cnt <= '0; l_last <= '0; l_min <= '1; l_max <= '0; l_cnt <= '0; d_last <= '0;
            start_q <= 1'b0;
        end else begin
            if (clr_p) begin
                n_sent_order <= '0; n_sent_feed <= '0; n_sent_probe <= '0; n_sent_test <= '0; n_poisoned <= '0; n_dropped <= '0;
                n_underrun <= '0; n_late <= '0; e_min <= '1; e_max <= '0; e_cnt <= '0; l_min <= '1; l_max <= '0; l_cnt <= '0;
            end
            if (go_p) begin
                go_cnt <= go_cnt + 32'd1; go_seq_l <= go_cnt + 32'd1;
                if (fs_busy || s_valid) n_dropped <= n_dropped + 32'd1;
            end
            // the order count restarts with the counter clear and with a restart of either side; the receive side restarts its order number
            // on the same events, so the two stay in step (97C). A clear in the clock of a go pulse wins: that order is flagged stale (fail closed)
            if (clr_p || seq_p) begin go_cnt <= '0; go_seq_l <= '0; end
            // Self-heal (97C review): a restart pulse that straddles a go pulse in the two domains (a few clocks apart) would leave the count one off for
            // good. An order flagged stale (it is poisoned, fail closed) reloads the count from the number it carries, so the NEXT order is in step.
            // The flagged order itself is never saved; an unsettled bus only costs the orders it garbles.
            else if (stale_p && is_order) go_cnt <= seq_seen;
            if (gen_go_p) begin gen_left <= gen_count; gen_wait <= '0; end
            if (gen_wait != 32'd0) gen_wait <= gen_wait - 32'd1;
            if (fs_start && !go_p && gen_due) begin
                gen_left <= gen_left - 32'd1; gen_wait <= gen_interval; gen_seq <= gen_seq + 32'd1;
            end
            if (fs_start) cur_kind <= fs_kind;
            if (underrun) n_underrun <= n_underrun + 32'd1;
            if (sop && own_a) begin
                case (cur_kind)
                    2'd0: begin t_tx_order <= ts; n_sent_order <= n_sent_order + 32'd1; end
                    2'd1: begin t_tx_feed <= ts; n_sent_feed <= n_sent_feed + 32'd1; end
                    2'd2: begin t_tx_probe <= ts; n_sent_probe <= n_sent_probe + 32'd1; end
                    default: n_sent_test <= n_sent_test + 32'd1;
                endcase
            end
            // an order whose verdict had not arrived when its last word was built would be sent unchecked: counted
            if (s_valid && s_last && s_ready && cur_kind == 2'd0) begin
                if (!verdict_good && !(verdict_v && verdict_bad && verdict_seq == go_seq_l)) n_late <= n_late + 32'd1;
                if (poison) n_poisoned <= n_poisoned + 32'd1;
            end
            // receive events (same clock since 96C)
            if (rx_sop_p) t_rx_sop <= ts;
            if (rx_feed_p) t_rx_feed <= t_rx_sop;
            if (rx_probe_p) begin
                t_rx_probe <= t_rx_sop; e_last <= t_rx_sop - t_tx_probe; e_cnt <= e_cnt + 32'd1;
                if (t_rx_sop - t_tx_probe < e_min) e_min <= t_rx_sop - t_tx_probe;
                if (t_rx_sop - t_tx_probe > e_max) e_max <= t_rx_sop - t_tx_probe;
            end
            if (rx_order_p) begin
                t_rx_order <= t_rx_sop; l_last <= t_rx_sop - t_tx_feed; l_cnt <= l_cnt + 32'd1;
                if (t_rx_sop - t_tx_feed < l_min) l_min <= t_rx_sop - t_tx_feed;
                if (t_rx_sop - t_tx_feed > l_max) l_max <= t_rx_sop - t_tx_feed;
                d_last <= t_tx_order - t_rx_feed;
            end
        end
    end
    // status vector (snapshot into the register domain), 32-bit words in this order (docs/register_map.md, TXV0 ...)
    logic [31:0] tw [NTXW];
    always_comb begin
        tw[0] = n_sent_order; tw[1] = n_sent_feed; tw[2] = n_sent_probe; tw[3] = n_sent_test; tw[4] = n_poisoned; tw[5] = n_dropped;
        tw[6] = n_underrun; tw[7] = n_late; tw[8] = stale; tw[9] = go_cnt; tw[10] = t_tx_feed; tw[11] = t_tx_probe; tw[12] = t_tx_order;
        tw[13] = t_rx_feed; tw[14] = t_rx_probe; tw[15] = t_rx_order; tw[16] = e_last; tw[17] = e_min; tw[18] = e_max; tw[19] = e_cnt;
        tw[20] = l_last; tw[21] = l_min; tw[22] = l_max; tw[23] = l_cnt; tw[24] = d_last; tw[25] = ts;
    end
    always_comb for (int i = 0; i < NTXW; i++) tx_vec[32 * i +: 32] = tw[i];
endmodule
