// trigger_core.sv: the mock trading path, in one clock domain (125 MHz, 8 ns a byte at 1 Gb/s).
//
// Port A (the trading port): receive MAC (cut-through) -> feed parser -> book and rules -> interlocks -> orders,
// speculative undo, cancels and ARP replies -> transmit MAC.
// Port B (the bench source): the in-FPGA mock feed generator -> transmit MAC; its receive side counts the orders that
// come back and times the loop (B out, A in, A out, B in) on the same counter.
// Both ports' receive bytes arrive here already in this clock domain (gmii_cdc, one asynchronous FIFO per port).
// Host access: a 32-bit register bus (docs/register_map.md), driven by the JTAG front end on the board and directly
// by the cocotb tests.

module trigger_core #(
    parameter logic [31:0] BUILD_STAMP = 32'h0,
    parameter int          BUILD_MODE  = 0,     // order_ctl: 0 pre-built headers, 1 assemble then send
    parameter int          NINST       = 256,
    parameter int          MDIO_DIV    = 32
) (
    input  logic        clk,
    input  logic        rst,
    // port A receive (after the clock crossing) and transmit
    input  logic        a_rx_v, a_rx_eof, a_rx_er,
    input  logic [7:0]  a_rx_d,
    input  logic        a_rx_ovf,
    output logic [7:0]  a_txd,
    output logic        a_tx_en,
    // port B
    input  logic        b_rx_v, b_rx_eof, b_rx_er,
    input  logic [7:0]  b_rx_d,
    input  logic        b_rx_ovf,
    output logic [7:0]  b_txd,
    output logic        b_tx_en,
    // management
    output logic        a_mdc, a_mdio_o, a_mdio_t,
    input  logic        a_mdio_i,
    output logic        b_mdc, b_mdio_o, b_mdio_t,
    input  logic        b_mdio_i,
    output logic        phy_rst_force,      // host holds both PHYs in reset
    input  logic [31:0] a_rxclk_cnt,        // receive-clock edge counters, already in this domain
    input  logic [31:0] b_rxclk_cnt,
    // operating conditions (SYSMON DRP, in this domain) and its alarms
    output logic        drp_en, drp_we,
    output logic [7:0]  drp_addr,
    output logic [15:0] drp_di,
    input  logic [15:0] drp_do,
    input  logic        drp_rdy,
    input  logic [7:0]  alarms,
    // kill input (synchronised) and pins
    input  logic        kill_in,
    output logic [1:0]  pins,
    // host register bus
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata
);
    // ---- time ---------------------------------------------------------------------------------------------------
    logic [31:0] ts;
    always_ff @(posedge clk) ts <= rst ? 32'd0 : ts + 32'd1;

    // ---- registers ----------------------------------------------------------------------------------------------
    logic        core_en, spec_en, halt_on_gap, kill_reg, hist_metric;
    logic [47:0] my_mac, dst_mac, gen_src_mac;
    logic [31:0] my_ip, dst_ip, gen_src_ip;
    logic [15:0] my_port, dst_port, gen_src_port;
    logic [31:0] max_qty, band, max_pos, refill, pin_width;
    logic [15:0] bucket;
    logic        gen_en;
    logic [31:0] gen_interval, gen_npkts, gen_base_px, gen_px_mask;
    logic [7:0]  gen_nmsg;
    logic [15:0] gen_inst_mask, gen_bad_every, gen_gap_every;
    logic        clr_cnt, clr_book, clr_hist, clr_halt, clr_kill_in;
    logic        rules_we, rules_commit;
    logic [31:0] commit_ts;
    logic [15:0] book_inst;
    logic        a_mdio_go, b_mdio_go;
    logic [31:0] a_mdio_cmd, b_mdio_cmd;
    logic [15:0] a_mdio_rd, b_mdio_rd;
    logic        a_mdio_busy, b_mdio_busy;
    logic [15:0] drp_q;
    logic        drp_busy;
    logic [7:0]  alarm_latch;
    logic        log_pop;

    // ---- port A: receive ------------------------------------------------------------------------------------------
    logic        ar_sof, ar_v, ar_first, ar_end, ar_good, ar_fcs, ar_runt, ar_giant, ar_er, ar_badpre;
    logic [7:0]  ar_d;
    logic [10:0] ar_idx, ar_len;
    mac_rx u_arx (.clk, .rst, .in_valid(a_rx_v), .in_eof(a_rx_eof), .in_er(a_rx_er), .in_data(a_rx_d),
                  .sof_pulse(ar_sof), .out_valid(ar_v), .out_sof(ar_first), .out_data(ar_d), .out_idx(ar_idx),
                  .end_valid(ar_end), .end_good(ar_good), .end_fcs_err(ar_fcs), .end_runt(ar_runt),
                  .end_giant(ar_giant), .end_er(ar_er), .end_len(ar_len), .ev_bad_pre(ar_badpre));
    logic [31:0] a_sof_ts;
    always_ff @(posedge clk) if (ar_sof) a_sof_ts <= ts;

    logic        p_hdr, m_inst_v, m_px_v, m_end_v, m_first, f_end, f_good, f_feed, f_arp;
    logic [31:0] p_seq, m_px, m_sz, m_rf, m_seq;
    logic [7:0]  p_cnt, m_type;
    logic        m_side;
    logic [15:0] m_inst;
    logic [47:0] arp_sha;
    logic [31:0] arp_spa;
    logic [6:0]  drop;
    feed_rx u_parse (.clk, .rst, .my_mac, .my_ip, .my_port,
                     .in_valid(ar_v && core_en), .in_sof(ar_first), .in_data(ar_d), .in_idx(ar_idx),
                     .in_end_v(ar_end), .in_end_good(ar_good),
                     .pkt_hdr_v(p_hdr), .pkt_seq(p_seq), .pkt_cnt(p_cnt),
                     .msg_inst_v(m_inst_v), .msg_px_v(m_px_v), .msg_end_v(m_end_v), .msg_type(m_type),
                     .msg_side(m_side), .msg_inst(m_inst), .msg_px(m_px), .msg_size(m_sz), .msg_ref(m_rf),
                     .msg_seq(m_seq), .msg_first(m_first),
                     .frame_end_v(f_end), .frame_good(f_good), .frame_feed(f_feed), .frame_arp_req(f_arp),
                     .arp_sha(arp_sha), .arp_spa(arp_spa),
                     .ev_drop_l2(drop[0]), .ev_drop_type(drop[1]), .ev_drop_ip(drop[2]), .ev_drop_csum(drop[3]),
                     .ev_drop_port(drop[4]), .ev_drop_feed(drop[5]), .ev_drop_arp(drop[6]));
    logic [31:0] dec_ts;                // clock of the latest decision point (price field complete)
    always_ff @(posedge clk) if (m_px_v) dec_ts <= ts;

    // sequence gaps: a packet header is checked against the sequence expected after the last good feed frame, so a
    // bad (discarded) frame shows up as a gap at the next packet, like a lost packet
    logic        have_seq, gap_ev, halted;
    logic [31:0] exp_seq, pend_seq;
    always_ff @(posedge clk) begin
        gap_ev <= 1'b0;
        if (rst) begin have_seq <= 1'b0; exp_seq <= '0; pend_seq <= '0; halted <= 1'b0; end
        else begin
            if (clr_halt) halted <= 1'b0;
            if (p_hdr) begin
                if (have_seq && p_seq != exp_seq) begin
                    gap_ev <= 1'b1;
                    if (halt_on_gap) halted <= 1'b1;
                end
                pend_seq <= p_seq + {24'd0, p_cnt};
            end
            if (f_end && f_good && f_feed) begin have_seq <= 1'b1; exp_seq <= pend_seq; end
        end
    end

    // book
    logic [31:0] bk_bpx, bk_bsz, bk_apx, bk_asz, bk_last;
    logic        bk_valid, bk_mism, bk_range, bk_badty, bk_busy;
    logic [159:0] bk_h;
    book #(.NINST(NINST)) u_book (.clk, .rst, .clear(clr_book), .busy(bk_busy),
        .rd_v(m_inst_v), .rd_inst(m_inst),
        .q_bid_px(bk_bpx), .q_bid_sz(bk_bsz), .q_ask_px(bk_apx), .q_ask_sz(bk_asz), .q_last(bk_last),
        .q_valid(bk_valid),
        .upd_v(m_end_v), .upd_type(m_type), .upd_side(m_side), .upd_px(m_px), .upd_sz(m_sz),
        .ev_mismatch(bk_mism), .ev_range(bk_range), .ev_bad_type(bk_badty),
        .h_inst(book_inst), .h_q(bk_h));

    // rules
    logic        fire_v, fire_order, fire_side, fire_pin_en, fire_pin_idx, fire_log, ev_hold;
    logic [2:0]  fire_rule;
    logic [15:0] fire_ver, rules_ver, fire_inst;
    logic [31:0] fire_qty, fire_px, fire_ref, rules_rd;
    logic [31:0] fire_seq;
    logic        fire_noref;
    rules #(.NR(8)) u_rules (.clk, .rst, .h_we(rules_we), .h_addr({2'b00, h_addr[5:0]}), .h_wdata(h_wdata),
        .h_commit(rules_commit), .version(rules_ver), .h_rdata(rules_rd),
        .msg_px_v(m_px_v), .msg_type(m_type), .msg_side(m_side), .msg_inst(m_inst), .msg_px(m_px),
        .bk_valid(bk_valid), .bk_bid_px(bk_bpx), .bk_bid_sz(bk_bsz), .bk_ask_px(bk_apx), .bk_ask_sz(bk_asz),
        .bk_last(bk_last),
        .fire_v(fire_v), .fire_rule(fire_rule), .fire_ver(fire_ver), .fire_order(fire_order), .fire_side(fire_side),
        .fire_qty(fire_qty), .fire_px(fire_px), .fire_ref_px(fire_ref), .fire_noref(fire_noref), .fire_inst(fire_inst),
        .fire_pin_en(fire_pin_en), .fire_pin_idx(fire_pin_idx), .fire_log(fire_log), .ev_holdoff(ev_hold));
    always_ff @(posedge clk) if (m_px_v) fire_seq <= m_seq;

    // interlocks
    logic        req_v, grant, rej_v;
    logic [2:0]  rej_why;
    logic signed [33:0] pos;
    logic [15:0] tokens;
    logic        kill_lat;
    always_ff @(posedge clk) begin
        if (rst || clr_kill_in) kill_lat <= 1'b0;
        else if (kill_in)       kill_lat <= 1'b1;
    end
    logic bucket_wr_q;
    always_ff @(posedge clk) bucket_wr_q <= h_we && h_addr == 12'h023;   // the new size is in the register by then
    interlocks u_il (.clk, .rst, .kill_reg(kill_reg), .kill_in(kill_lat | kill_in), .halt(halted),
        .max_qty, .band, .max_pos, .bucket, .refill, .reload(bucket_wr_q),
        .req_v, .req_side(fire_side), .req_qty(fire_qty), .req_px(fire_px), .req_ref(fire_ref), .req_noref(fire_noref),
        .grant, .rej_v, .rej_why, .pos, .tokens, .approved(), .tick());
    logic kill_now;
    assign kill_now = kill_reg | kill_lat | kill_in;

    // orders and the transmit MAC
    logic        at_start, at_ready, at_reqv, at_poison, at_first, at_sof, at_last, at_lastp, at_busy;
    logic [10:0] at_len, at_idx;
    logic [7:0]  at_data;
    logic        at_lastb, bt_lastb;
    logic [1:0]  at_kind;
    logic [31:0] cur_oid;
    logic [8:0]  oev;
    logic        soft_rst;          // PULSE[7]: reset the order slot and what is pending (board-safe)
    logic [7:0]  s_gen, fgen;
    logic        s_act, s_gnt, s_vk, s_vg, s_start, s_sent, c_pend, ev_wdog;
    order_ctl #(.BUILD_MODE(BUILD_MODE)) u_ord (.clk, .rst, .soft_rst, .spec_en, .kill_now,
        .my_mac, .my_ip, .my_port, .dst_mac, .dst_ip, .dst_port,
        .fire_v, .fire_order, .req_v, .grant, .rej_v,
        .o_side(fire_side), .o_inst(fire_inst), .o_px(fire_px), .o_qty(fire_qty),
        .frame_end_v(f_end), .frame_good(f_good), .frame_arp_req(f_arp), .arp_sha, .arp_spa,
        .tx_start(at_start), .tx_len(at_len), .tx_ready(at_ready), .tx_req_valid(at_reqv), .tx_req_idx(at_idx),
.tx_data(at_data), .tx_last_byte(at_lastb), .tx_poison(at_poison), .tx_last(at_last),
        .tx_last_poisoned(at_lastp), .tx_kind(at_kind), .cur_order_id(cur_oid),
        .ev_suppress(oev[0]), .ev_busy(oev[1]), .ev_spec_drop(oev[2]), .ev_spec_poison(oev[3]),
        .ev_spec_cancel(oev[4]), .ev_kill_drop(oev[5]), .ev_order_sent(oev[6]), .ev_cancel_sent(oev[7]),
        .ev_arp_sent(oev[8]), .ev_wdog(ev_wdog), .s_act, .s_gnt, .s_vk, .s_vg, .s_start, .s_sent, .s_gen, .fgen,
        .cancel_pend(c_pend));
    mac_tx u_atx (.clk, .rst, .ce(1'b1), .start(at_start), .ready(at_ready), .req_idx(at_idx),
        .req_valid(at_reqv), .in_data(at_data), .in_last(at_lastb), .poison(at_poison), .txd(a_txd), .tx_en(a_tx_en),
        .first_pulse(at_first), .sof_pulse(at_sof), .last_pulse(at_last), .last_poisoned(at_lastp), .busy(at_busy));

    // trigger time of the order in the slot (the RX SFD and the decision clock of its trigger frame)
    logic [31:0] o_trig_ts, o_dec_ts;
    always_ff @(posedge clk) if (grant) begin o_trig_ts <= a_sof_ts; o_dec_ts <= dec_ts; end

    // ---- port B: the bench source and the loop timer ------------------------------------------------------------------
    logic        bt_start, bt_ready, bt_reqv, bt_poison, bt_first, bt_sof, bt_last, bt_lastp, bt_busy;
    logic [10:0] bt_len, bt_idx;
    logic [7:0]  bt_data;
    logic [31:0] gen_sent;
    feed_gen u_gen (.clk, .rst, .en(gen_en), .interval(gen_interval), .npkts(gen_npkts), .nmsg(gen_nmsg),
        .inst_mask(gen_inst_mask), .base_px(gen_base_px), .px_mask(gen_px_mask), .bad_every(gen_bad_every),
        .gap_every(gen_gap_every), .src_mac(gen_src_mac), .dst_mac(my_mac), .src_ip(gen_src_ip), .dst_ip(my_ip),
        .src_port(gen_src_port), .dst_port(my_port), .sent(gen_sent),
        .tx_start(bt_start), .tx_len(bt_len), .tx_ready(bt_ready), .tx_req_valid(bt_reqv), .tx_req_idx(bt_idx),
        .tx_data(bt_data), .tx_last_byte(bt_lastb), .tx_poison(bt_poison));
    mac_tx u_btx (.clk, .rst, .ce(1'b1), .start(bt_start), .ready(bt_ready), .req_idx(bt_idx),
        .req_valid(bt_reqv), .in_data(bt_data), .in_last(bt_lastb), .poison(bt_poison), .txd(b_txd), .tx_en(b_tx_en),
        .first_pulse(bt_first), .sof_pulse(bt_sof), .last_pulse(bt_last), .last_poisoned(bt_lastp), .busy(bt_busy));
    logic [31:0] b_tx_first_ts;
    always_ff @(posedge clk) if (bt_first) b_tx_first_ts <= ts;

    logic        br_sof, br_v, br_first, br_end, br_good, br_fcs;
    logic [7:0]  br_d;
    logic [10:0] br_idx, br_len;
    mac_rx u_brx (.clk, .rst, .in_valid(b_rx_v), .in_eof(b_rx_eof), .in_er(b_rx_er), .in_data(b_rx_d),
        .sof_pulse(br_sof), .out_valid(br_v), .out_sof(br_first), .out_data(br_d), .out_idx(br_idx),
        .end_valid(br_end), .end_good(br_good), .end_fcs_err(br_fcs), .end_runt(), .end_giant(), .end_er(),
        .end_len(br_len), .ev_bad_pre());
    logic [31:0] b_rx_sof_ts;
    logic        b_is_order;
    always_ff @(posedge clk) begin
        if (br_sof) begin b_rx_sof_ts <= ts; b_is_order <= 1'b0; end
        if (br_v && br_idx == 11'd50) b_is_order <= (br_d == 8'h10);
    end

    // ---- histograms ------------------------------------------------------------------------------------------------
    // A: tick-to-trade at the MAC boundaries, per order: metric 0 = trigger frame's RX SFD -> order's first preamble
    //    byte; metric 1 = decision clock (price complete) -> first preamble byte.
    // B: the bench loop on port B: feed packet's first preamble byte out -> the order's SFD back in.
    logic        ha_v, hb_v;
    logic [31:0] ha_val, hb_val;
    assign ha_v   = at_first && at_kind == 2'd1;
    assign ha_val = hist_metric ? ts - o_dec_ts : ts - o_trig_ts;
    assign hb_v   = br_end && br_good && b_is_order;
    assign hb_val = b_rx_sof_ts - b_tx_first_ts;
    logic [31:0] ha_q, ha_cnt, ha_min, ha_max, ha_lost, hb_q, hb_cnt, hb_min, hb_max, hb_lost;
    logic [47:0] ha_sum, hb_sum;
    logic        ha_busy, hb_busy;
    lat_hist #(.NB(256)) u_ha (.clk, .rst, .clear(clr_hist), .s_v(ha_v), .s_val(ha_val), .h_bin(h_addr[7:0]),
        .h_q(ha_q), .count(ha_cnt), .sum(ha_sum), .vmin(ha_min), .vmax(ha_max), .lost(ha_lost), .busy(ha_busy));
    lat_hist #(.NB(256)) u_hb (.clk, .rst, .clear(clr_hist), .s_v(hb_v), .s_val(hb_val), .h_bin(h_addr[7:0]),
        .h_q(hb_q), .count(hb_cnt), .sum(hb_sum), .vmin(hb_min), .vmax(hb_max), .lost(hb_lost), .busy(hb_busy));
    // last sample of each, for the tests and the host
    logic [31:0] ha_last, hb_last;
    always_ff @(posedge clk) begin
        if (ha_v) ha_last <= ha_val;
        if (hb_v) hb_last <= hb_val;
    end

    // ---- decision log: one entry per rule firing with its log flag --------------------------------------------------
    // entry: {ts}, {seq}, {version, rule, inst[11:0]}, {price}
    localparam int LOGN = 64;
    logic [127:0] logm [LOGN];
    logic [6:0]   lw, lr;
    logic [31:0]  log_drops;
    logic [127:0] log_head;
    always_ff @(posedge clk) begin
        if (rst) begin lw <= '0; lr <= '0; end
        else begin
            if (fire_v && fire_log && (lw - lr) != 7'(LOGN)) begin
                logm[lw[5:0]] <= {ts, fire_seq, fire_ver, 1'b0, fire_rule, fire_inst[11:0], fire_px};
                lw <= lw + 7'd1;
            end
            if (log_pop && lw != lr) lr <= lr + 7'd1;
        end
    end
    assign log_head = logm[lr[5:0]];
    logic log_full_ev;
    assign log_full_ev = fire_v && fire_log && (lw - lr) == 7'(LOGN);

    // ---- pins -------------------------------------------------------------------------------------------------------
    logic [31:0] pin_t [2];
    always_ff @(posedge clk) begin
        for (int j = 0; j < 2; j++) begin
            if (rst) pin_t[j] <= '0;
            else if (fire_v && fire_pin_en && fire_pin_idx == j[0]) pin_t[j] <= pin_width;
            else if (pin_t[j] != 0) pin_t[j] <= pin_t[j] - 32'd1;
        end
    end
    assign pins = {pin_t[1] != 0, pin_t[0] != 0};

    // ---- counters -------------------------------------------------------------------------------------------------------
    localparam int NC = 54;
    logic [NC-1:0] ev;
    logic [31:0]   cnt [NC];
    logic [31:0]   ar_len32;
    assign ar_len32 = {21'd0, ar_len};
    always_comb begin
        ev = '0;
        ev[0] = ar_end;            ev[1] = ar_end && ar_good;  ev[3] = ar_end && ar_fcs;   ev[4] = ar_end && ar_runt;
        ev[5] = ar_end && ar_giant; ev[6] = ar_end && ar_er;   ev[7] = ar_badpre;
        ev[8] = drop[0]; ev[9] = drop[1]; ev[10] = drop[2]; ev[11] = drop[3]; ev[12] = drop[4]; ev[13] = drop[5];
        ev[14] = drop[6]; ev[15] = f_end && f_good && f_arp;
        ev[16] = p_hdr; ev[17] = m_end_v; ev[18] = gap_ev; ev[19] = bk_mism; ev[20] = bk_range; ev[21] = bk_badty;
        ev[22] = fire_v; ev[23] = ev_hold; ev[24] = req_v; ev[25] = grant;
        ev[26] = rej_v && rej_why == 3'd1; ev[27] = rej_v && rej_why == 3'd2; ev[28] = rej_v && rej_why == 3'd3;
        ev[29] = rej_v && rej_why == 3'd4; ev[30] = rej_v && rej_why == 3'd5; ev[31] = rej_v && rej_why == 3'd6;
        ev[32] = oev[0]; ev[33] = oev[1]; ev[34] = oev[2]; ev[35] = oev[3]; ev[36] = oev[4]; ev[37] = oev[5];
        ev[38] = oev[6]; ev[39] = oev[7]; ev[40] = oev[8]; ev[41] = at_last; ev[42] = at_last && at_lastp;
        ev[43] = a_rx_ovf;
        ev[44] = br_end; ev[45] = br_end && br_good; ev[46] = br_end && br_fcs; ev[47] = hb_v; ev[48] = bt_first;
        ev[49] = bt_last; ev[50] = b_rx_ovf; ev[51] = log_full_ev; ev[52] = ev_wdog; ev[53] = soft_rst;
    end
    always_ff @(posedge clk) begin
        for (int j = 0; j < NC; j++) begin
            if (rst || clr_cnt) cnt[j] <= '0;
            else if (j == 2) begin if (ar_end) cnt[j] <= cnt[j] + ar_len32; end
            else if (ev[j])  cnt[j] <= cnt[j] + 32'd1;
        end
    end

    // ---- management -------------------------------------------------------------------------------------------------------
    mdio_master #(.DIV(MDIO_DIV)) u_amd (.clk, .rst, .go(a_mdio_go), .rd(a_mdio_cmd[30]), .phy(a_mdio_cmd[25:21]),
        .reg_a(a_mdio_cmd[20:16]), .wdata(a_mdio_cmd[15:0]), .rdata(a_mdio_rd), .busy(a_mdio_busy),
        .mdc(a_mdc), .mdio_o(a_mdio_o), .mdio_t(a_mdio_t), .mdio_i(a_mdio_i));
    mdio_master #(.DIV(MDIO_DIV)) u_bmd (.clk, .rst, .go(b_mdio_go), .rd(b_mdio_cmd[30]), .phy(b_mdio_cmd[25:21]),
        .reg_a(b_mdio_cmd[20:16]), .wdata(b_mdio_cmd[15:0]), .rdata(b_mdio_rd), .busy(b_mdio_busy),
        .mdc(b_mdc), .mdio_o(b_mdio_o), .mdio_t(b_mdio_t), .mdio_i(b_mdio_i));
    always_ff @(posedge clk) begin
        drp_en <= 1'b0; drp_we <= 1'b0;
        if (rst) begin drp_busy <= 1'b0; drp_q <= '0; drp_addr <= '0; drp_di <= '0; alarm_latch <= '0; end
        else begin
            alarm_latch <= alarm_latch | alarms;
            if (h_we && h_addr == 12'h1A0 && !drp_busy) begin
                drp_en <= 1'b1; drp_we <= h_wdata[31]; drp_addr <= h_wdata[23:16]; drp_di <= h_wdata[15:0];
                drp_busy <= 1'b1;
            end
            if (drp_rdy) begin drp_busy <= 1'b0; drp_q <= drp_do; end
            if (h_we && h_addr == 12'h1A2) alarm_latch <= alarms;           // clear to the present alarms
        end
    end

    // ---- register writes ----------------------------------------------------------------------------------------------------
    always_ff @(posedge clk) begin
        {clr_cnt, clr_book, clr_hist, clr_halt, clr_kill_in, rules_commit, a_mdio_go, b_mdio_go, log_pop, soft_rst} <= '0;
        if (rst) begin
            core_en <= 1'b0; spec_en <= 1'b1; halt_on_gap <= 1'b0; kill_reg <= 1'b0; hist_metric <= 1'b0;
            phy_rst_force <= 1'b0;
            my_mac <= 48'h02_00_00_00_58_0A; dst_mac <= 48'h02_00_00_00_58_0F; gen_src_mac <= 48'h02_00_00_00_58_0B;
            my_ip <= 32'hC0A8_3A0A; dst_ip <= 32'hC0A8_3A0F; gen_src_ip <= 32'hC0A8_3A0B;
            my_port <= 16'd5800; dst_port <= 16'd5801; gen_src_port <= 16'd5802;
            max_qty <= 32'd100; band <= 32'd500; max_pos <= 32'd1000; bucket <= 16'd16; refill <= 32'd125000;
            pin_width <= 32'd12_500_000;
            gen_en <= 1'b0; gen_interval <= 32'd1250; gen_npkts <= '0; gen_nmsg <= 8'd1; gen_inst_mask <= 16'h7;
            gen_base_px <= 32'd10000; gen_px_mask <= 32'hFF; gen_bad_every <= '0; gen_gap_every <= '0;
            commit_ts <= '0; book_inst <= '0; a_mdio_cmd <= '0; b_mdio_cmd <= '0;
        end else begin
            if (rules_commit) commit_ts <= ts;
            if (h_we) begin
                case (h_addr)
                    12'h002: begin
                        core_en <= h_wdata[0]; spec_en <= h_wdata[1]; halt_on_gap <= h_wdata[2]; kill_reg <= h_wdata[3];
                        hist_metric <= h_wdata[4]; phy_rst_force <= h_wdata[5];
                    end
                    12'h003: begin
                        clr_cnt <= h_wdata[0]; clr_book <= h_wdata[1]; clr_hist <= h_wdata[2]; clr_halt <= h_wdata[3];
                        clr_kill_in <= h_wdata[4]; rules_commit <= h_wdata[5]; log_pop <= h_wdata[6];
                        soft_rst <= h_wdata[7];
                    end
                    12'h010: my_mac[47:16] <= h_wdata;
                    12'h011: my_mac[15:0]  <= h_wdata[15:0];
                    12'h012: my_ip         <= h_wdata;
                    12'h013: my_port       <= h_wdata[15:0];
                    12'h014: dst_mac[47:16] <= h_wdata;
                    12'h015: dst_mac[15:0]  <= h_wdata[15:0];
                    12'h016: dst_ip        <= h_wdata;
                    12'h017: dst_port      <= h_wdata[15:0];
                    12'h020: max_qty <= h_wdata;
                    12'h021: band    <= h_wdata;
                    12'h022: max_pos <= h_wdata;
                    12'h023: bucket  <= h_wdata[15:0];
                    12'h024: refill  <= h_wdata;
                    12'h025: pin_width <= h_wdata;
                    12'h030: book_inst <= h_wdata[15:0];
                    12'h180: begin a_mdio_cmd <= h_wdata; a_mdio_go <= 1'b1; end
                    12'h182: begin b_mdio_cmd <= h_wdata; b_mdio_go <= 1'b1; end
                    12'h1C0: gen_en        <= h_wdata[0];
                    12'h1C1: gen_interval  <= h_wdata;
                    12'h1C2: gen_npkts     <= h_wdata;
                    12'h1C3: gen_nmsg      <= h_wdata[7:0];
                    12'h1C4: gen_inst_mask <= h_wdata[15:0];
                    12'h1C5: gen_base_px   <= h_wdata;
                    12'h1C6: gen_px_mask   <= h_wdata;
                    12'h1C7: begin gen_bad_every <= h_wdata[31:16]; gen_gap_every <= h_wdata[15:0]; end
                    12'h1C8: gen_src_mac[47:16] <= h_wdata;
                    12'h1C9: gen_src_mac[15:0]  <= h_wdata[15:0];
                    12'h1CA: gen_src_ip    <= h_wdata;
                    12'h1CB: gen_src_port  <= h_wdata[15:0];
                    default: ;
                endcase
            end
        end
    end
    assign rules_we = h_we && h_addr[11:8] == 4'h0 && h_addr[7:6] == 2'b01;     // 0x040..0x07F

    // ---- register reads (one clock) ---------------------------------------------------------------------------------------------
    logic [31:0] rd;
    always_comb begin
        rd = 32'h0;
        if (h_addr[11:8] == 4'h1 && h_addr[7:6] == 2'b00) begin                // 0x100..0x13F counters
            rd = (h_addr[5:0] < 6'(NC)) ? cnt[h_addr[5:0]] : 32'h0;
        end else if (h_addr[11:8] == 4'h0 && h_addr[7:6] == 2'b01) begin       // 0x040..0x07F rules (active)
            rd = rules_rd;
        end else begin
            case (h_addr)
                12'h000: rd = 32'h58A0_0001;
                12'h001: rd = BUILD_STAMP;
                12'h002: rd = {26'd0, phy_rst_force, hist_metric, kill_reg, halt_on_gap, spec_en, core_en};
                12'h004: rd = {24'd0, bk_busy, ha_busy | hb_busy, a_mdio_busy, b_mdio_busy, drp_busy, kill_lat, halted,
                               kill_now};
                12'h005: rd = ts;
                12'h006: rd = {16'd0, rules_ver};
                12'h007: rd = commit_ts;
                12'h008: rd = BUILD_MODE;
                12'h009: rd = {fgen, s_gen, 8'd0, c_pend, s_sent, s_start, s_vg, s_vk, s_gnt, 1'b0, s_act};
                12'h010: rd = my_mac[47:16];
                12'h011: rd = {16'd0, my_mac[15:0]};
                12'h012: rd = my_ip;
                12'h013: rd = {16'd0, my_port};
                12'h014: rd = dst_mac[47:16];
                12'h015: rd = {16'd0, dst_mac[15:0]};
                12'h016: rd = dst_ip;
                12'h017: rd = {16'd0, dst_port};
                12'h020: rd = max_qty;
                12'h021: rd = band;
                12'h022: rd = max_pos;
                12'h023: rd = {16'd0, bucket};
                12'h024: rd = refill;
                12'h025: rd = pin_width;
                12'h026: rd = pos[31:0];
                12'h027: rd = {16'd0, tokens};
                12'h028: rd = exp_seq;
                12'h030: rd = {16'd0, book_inst};
                12'h031: rd = bk_h[31:0];
                12'h032: rd = bk_h[63:32];
                12'h033: rd = bk_h[95:64];
                12'h034: rd = bk_h[127:96];
                12'h035: rd = bk_h[159:128];
                12'h140: rd = {25'd0, lw - lr};
                12'h141: rd = log_head[127:96];
                12'h142: rd = log_head[95:64];
                12'h143: rd = log_head[63:32];
                12'h144: rd = log_head[31:0];
                12'h150: rd = ha_cnt;
                12'h151: rd = ha_sum[31:0];
                12'h152: rd = {16'd0, ha_sum[47:32]};
                12'h153: rd = ha_min;
                12'h154: rd = ha_max;
                12'h155: rd = ha_lost;
                12'h156: rd = ha_last;
                12'h158: rd = hb_cnt;
                12'h159: rd = hb_sum[31:0];
                12'h15A: rd = {16'd0, hb_sum[47:32]};
                12'h15B: rd = hb_min;
                12'h15C: rd = hb_max;
                12'h15D: rd = hb_lost;
                12'h15E: rd = hb_last;
                12'h180: rd = a_mdio_cmd;
                12'h181: rd = {a_mdio_busy, 15'd0, a_mdio_rd};
                12'h182: rd = b_mdio_cmd;
                12'h183: rd = {b_mdio_busy, 15'd0, b_mdio_rd};
                12'h184: rd = a_rxclk_cnt;
                12'h185: rd = b_rxclk_cnt;
                12'h1A0: rd = {drp_busy, 15'd0, drp_q};
                12'h1A1: rd = {24'd0, alarms};
                12'h1A2: rd = {24'd0, alarm_latch};
                12'h1C0: rd = {31'd0, gen_en};
                12'h1C2: rd = gen_npkts;
                12'h1CC: rd = gen_sent;
                default: rd = 32'h0;
            endcase
        end
    end
    // Read timing: the host holds h_addr and pulses h_re; h_rdata is valid two clocks after h_re (the histogram bin
    // RAMs need the first clock). Histogram bins: 0x400..0x4FF (A), 0x500..0x5FF (B).
    logic [1:0]  rsel;
    logic [31:0] r1;
    always_ff @(posedge clk) begin
        rsel <= (h_addr[11:8] == 4'h4) ? 2'd1 : (h_addr[11:8] == 4'h5) ? 2'd2 : 2'd0;
        r1   <= rd;
        h_rdata <= (rsel == 2'd1) ? ha_q : (rsel == 2'd2) ? hb_q : r1;
    end
endmodule
