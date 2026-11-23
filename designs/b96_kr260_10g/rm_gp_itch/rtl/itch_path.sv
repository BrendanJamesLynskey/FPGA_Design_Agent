// itch_path.sv: brief 110's standard-protocol path as the 10G core uses it (brief 127), all in the core (transmit user) clock, between mac64_rx and the transmit multiplexer.
//
//   mac64_rx words --udp_strip--> payload words --itch_top (mold_rx .. risk_glue, order_seg)--> order frame stream --> tx_mux --> mac64_tx
//                              \--> late FCS verdict (v_v, v_bad) --> untrusted flag, pkt_err, and the poison of the order frame in flight
// Also here: the host's configuration vector (CFG2) decoded, the command pulses, the counters and stamps (STAT2) packed, the order-frame poison policy and the latency
// statistics. Everything that crosses to the register clock does so as the two coherent vectors CFG2 and STAT2 (hs_vec in b96_core), so nothing here needs a crossing.
//
// ORDER POISON (the FCS verdict of the trigger frame, docs/itch_integration.md section 4). An order frame is poisoned (its FCS made wrong by mac64_tx, so the receiver drops it)
// when, with its last word:
//   * risk refused it or the book did not confirm it (abort), or a speculative frame had no verdict (order_seg's o_poison);
//   * the frame that carried the trigger message had a BAD verdict (FCS wrong, cut, shorter than its IP length) that was known by then, or any bad verdict arrived while the
//     order frame was in flight (this also covers an order that waited in risk_glue's queue, whose trigger frame cannot be told);
//   * in STRICT mode (CTRL.STRICT = 1), also when the trigger frame's verdict was not yet known and good: nothing leaves on an unverified frame.
// In cut-through mode (the default) an order whose trigger frame's verdict is still missing at its last word leaves unpoisoned and is counted (`unv`): this is the window of
// the risk, and it exists whenever the trigger message is far enough from the end of its packet that the order's last word (15 clocks after `go`) is out before the frame
// ends. Packets are tagged by a 4-bit count of started packets and verdicts by a count of verdicts (one per forwarded packet, in order); an 8-deep history of verdict results is
// indexed by their difference.
module itch_path
    import itch_pkg::*;
    import itch_pkg2::*;
#(
    parameter int N_INST = 4
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [31:0] ts,
    input  logic [b96_pkg::CFGW-1:0] cfg,        // the 96 design's configuration vector (core clock copy): MACs, IPs, ports
    // from mac64_rx
    input  logic        rx_sop,
    input  logic        m_v,
    input  logic [63:0] m_d,
    input  logic        m_sof,
    input  logic        m_end,
    input  logic        m_fcs_ok,
    input  logic [15:0] m_len,
    input  logic        m_err,
    // host vectors (already in this clock domain)
    input  logic [32*NCW-1:0] cfg2,
    output logic [32*NSW-1:0] stat2,
    // toward tx_mux
    output logic        o_v,
    output logic [63:0] o_d,
    output logic        o_sof,
    output logic        o_eof,
    output logic [7:0]  o_keep,
    output logic        o_poison,
    output logic        o_unres,
    output logic        fcs_poison,
    output logic        rp_start, rp_stop,
    output logic [15:0] rp_loops,
    output logic        wr_we,
    output logic [7:0]  wr_addr,
    output logic [63:0] wr_data,
    // from tx_mux
    input  logic        ord_start, ord_drop, ord_end, ord_end_seg, ord_end_unres, ord_end_fcs, ord_end_ofl, ord_sop, ord_busy,
    input  logic [31:0] rp_frames, rp_err, n_ofl,
    input  logic        rp_busy
);
    // ---------------------------------------------------------------- CFG2 decode
    logic [47:0] my_mac, venue_mac;
    logic [31:0] my_ip, venue_ip, thr_b, qty_b;
    logic [15:0] sport, port_feed, port_order, port_probe;
    logic        arm_b, kill_b, trade_en_b;
    logic [1:0]  gen_kind;
    logic [15:0] gen_len, gen_inst;
    logic [31:0] gen_price, gen_interval, gen_count;
    assign {gen_count, gen_interval, gen_price, gen_inst, gen_len, gen_kind, trade_en_b, kill_b, arm_b, qty_b, thr_b, port_probe, port_order,
            port_feed, sport, venue_ip, my_ip, venue_mac, my_mac} = cfg;
    logic [31:0] cw [NCW];
    always_comb for (int i = 0; i < NCW; i++) cw[i] = cfg2[32*i +: 32];
    logic        k_en, k_arm, k_kill, k_spec, k_halt, k_strict;
    assign {k_strict, k_halt, k_spec, k_kill, k_arm, k_en} = cw[C_CTRL][5:0];
    logic        k_refsw, c_commit;
    logic [15:0] k_holdoff;
    assign k_refsw = cw[C_CTRL][K_REFSW];
    assign k_holdoff = cw[C_CTRL][31:16];
    logic [N_INST*64-1:0] watch;
    always_comb for (int i = 0; i < N_INST; i++) watch[64*i +: 64] = {cw[C_WATCH + 2*i + 1], cw[C_WATCH + 2*i]};
    // commands: executed once when the sequence byte changes (the host writes them at least a microsecond apart)
    logic [7:0]  cmd_seq_q;
    logic [15:0] cmd;
    logic        cmd_go;
    assign cmd_go = (cw[C_CMD][23:16] != cmd_seq_q);
    always_ff @(posedge clk) cmd_seq_q <= (rst || cmd_go) ? cw[C_CMD][23:16] : cmd_seq_q;
    logic c_cnt, c_flags, c_book, c_pos, c_ref, c_tcp, c_lat, c_cap;
    always_comb begin
        cmd = cw[C_CMD][15:0];
        c_cnt = cmd_go && cmd[M_CLR_CNT]; c_flags = cmd_go && cmd[M_CLR_FLAGS]; c_book = cmd_go && cmd[M_CLR_BOOK]; c_pos = cmd_go && cmd[M_CLR_POS];
        c_ref = cmd_go && cmd[M_CLR_REF]; c_tcp = cmd_go && cmd[M_TCP_LOAD]; c_lat = cmd_go && cmd[M_LAT_CLR]; c_cap = cmd_go && cmd[M_CAP_CLR];
        rp_start = cmd_go && cmd[M_RP_START]; c_commit = cmd_go && cmd[M_COMMIT]; rp_stop = cmd_go && cmd[M_RP_STOP];
    end
    // replay memory write and the tcp_fast software bus: a write happens once when its sequence byte changes
    logic [7:0] rpw_q, tcpf_q;
    logic       tcpf_we;
    always_ff @(posedge clk) begin
        rpw_q <= cw[C_RPW][23:16]; tcpf_q <= cw[C_TCPFA][23:16];
    end
    assign wr_we   = (cw[C_RPW][23:16] != rpw_q) && !rst;
    assign rp_loops = cw[C_RPCFG][15:0];
    assign wr_addr = cw[C_RPW][7:0];
    assign wr_data = {cw[C_RPWHI], cw[C_RPWLO]};
    assign tcpf_we = (cw[C_TCPFA][23:16] != tcpf_q) && !rst;

    // ---------------------------------------------------------------- udp_strip
    logic        s_v, s_sof, s_eof, v_v, v_bad;
    logic [63:0] s_d;
    logic [7:0]  s_keep;
    logic [15*32-1:0] cnt_us;
    logic [63:0] cap_data;
    udp_strip u_us (.clk, .rst, .clr_cnt(c_cnt), .cfg_en(k_en), .cfg_mac(my_mac), .cfg_ip(cw[C_FEEDIP]), .cfg_port(cw[C_FEEDPORT][15:0]), .cap_clr(c_cap),
        .rx_sop, .m_v, .m_d, .m_sof, .m_end, .m_fcs_ok, .m_len, .m_err, .s_v, .s_d, .s_sof, .s_eof, .s_keep, .v_v, .v_bad,
        .cap_addr(cw[C_CAPADDR][6:0]), .cap_data, .cnt(cnt_us));

    // ---------------------------------------------------------------- the 110 path
    logic [NC*32-1:0] cnt_i;
    logic [15:0]      flags;
    logic             go, go_spec, commit, abort, b_late, refuse_v;
    logic [31:0]      tcpf_rd;
    logic             tx_unsent;
    // brief 176: a frame the multiplexer poisoned for a reason order_seg cannot see (the trigger frame's bad FCS, STRICT without a verdict, order FIFO overflow) consumes no TCP sequence
    // number: the builder gives it back. `ord_end_seg` frames were never counted by the builder. The give-back is a one-clock pulse in the clock the frame's last word is taken by the
    // MAC (ord_end) and adds no clock to the order path: the multiplexer grants the MAC to the next frame only after this verdict (a frame that starts earlier is dropped whole and consumes nothing).
    assign tx_unsent = ord_end && !ord_end_seg && (ord_end_ofl || ord_end_fcs);
    itch_top #(.N_INST(N_INST)) u_it (.clk, .rst, .s_v, .s_d, .s_sof, .s_eof, .s_keep, .v_v, .v_bad,
        .cfg_watch(watch), .cfg_thr(cw[C_THR]), .cfg_qty(cw[C_QTY]), .cfg_max_qty(cw[C_MAXQTY]), .cfg_max_pos(cw[C_MAXPOS]), .cfg_band(cw[C_BAND]), .cfg_px_off(cw[C_PXOFF]),
        .cfg_minqty(cw[C_MINQTY]), .cfg_tif(cw[C_ORDF0][7:0]), .cfg_display(cw[C_ORDF0][15:8]), .cfg_capacity(cw[C_ORDF0][23:16]), .cfg_ise(cw[C_ORDF0][31:24]),
        .cfg_cross(cw[C_ORDF1][7:0]), .cfg_custtype(cw[C_ORDF1][15:8]), .cfg_arm(k_arm), .cfg_kill(k_kill), .cfg_halt_on_gap(k_halt), .cfg_spec(k_spec), .cfg_holdoff(k_holdoff), .cfg_ref_sw(k_refsw), .cfg_ref_px(cw[C_REFPX]), .cfg_ref_age(cw[C_REFAGE]), .ref_load(c_commit),
        .tpl_my_mac(my_mac), .tpl_venue_mac(venue_mac), .tpl_my_ip(my_ip), .tpl_venue_ip(venue_ip), .tpl_sport(sport), .tpl_dport(port_order),
        .tpl_seq0(cw[C_TCPSEQ]), .tpl_ack(cw[C_TCPACK]), .tpl_load(c_tcp), .tx_unsent, .tx_drop(ord_drop), .sw_we(tcpf_we), .sw_waddr(cw[C_TCPFA][4:0]), .sw_wdata(cw[C_TCPFD]),
        .sw_raddr(cw[C_TCPFA][12:8]), .sw_rdata(tcpf_rd),
        .clr_cnt(c_cnt), .clr_flags(c_flags), .clr_book(c_book), .clr_pos(c_pos), .clr_ref(c_ref), .tx_busy(ord_busy),
        .o_v, .o_d, .o_sof, .o_eof, .o_keep, .o_poison, .o_unres, .go, .go_spec, .commit, .abort, .b_late, .refuse_v, .flags, .cnt(cnt_i));

    // ---------------------------------------------------------------- order poison policy
    logic [3:0]  pk_n, vn, o_pk;
    logic [7:0]  vh;
    logic        infl, bad_since, r_bad, r_unk;
    logic [3:0]  dd;
    logic        known, badk;
    assign dd    = vn - o_pk;
    assign known = !dd[3];
    assign badk  = vh[dd[2:0]];
    always_ff @(posedge clk) begin
        if (rst) begin
            pk_n <= '0; vn <= '0; vh <= '0; o_pk <= '0; infl <= 1'b0; bad_since <= 1'b0; r_bad <= 1'b0; r_unk <= 1'b0; fcs_poison <= 1'b0;
        end else begin
            if (s_v && s_sof) pk_n <= pk_n + 4'd1;
            if (v_v) begin vn <= vn + 4'd1; vh <= {vh[6:0], v_bad}; end
            if (ord_start) begin o_pk <= pk_n; infl <= 1'b1; bad_since <= 1'b0; end
            else if (ord_end) infl <= 1'b0;
            else if (infl && v_v && v_bad) bad_since <= 1'b1;
            r_bad <= bad_since || (known && badk);
            r_unk <= !known;
            fcs_poison <= infl && (bad_since || (known && badk) || (k_strict && !known));
        end
    end

    // ---------------------------------------------------------------- order counters and latency
    logic [31:0] n_sent, n_pz_abort, n_pz_bad, n_pz_strict, n_unv, n_drop, n_unres, n_late, n_refused;
    logic [31:0] ts_eof, ts_go, ts_sop, ts_rxsop, lat_last, lat_min, lat_max, lat_cnt, lat_neg;
    logic [15:0] hist [16];
    logic [31:0] lat_v;
    logic [3:0]  lat_bin;
    assign lat_v   = ts - ts_eof;
    assign lat_bin = (lat_v[31] || lat_v > 32'd14) ? 4'd15 : lat_v[3:0];
    always_ff @(posedge clk) begin
        if (rst) begin
            n_sent <= '0; n_pz_abort <= '0; n_pz_bad <= '0; n_pz_strict <= '0; n_unv <= '0; n_drop <= '0; n_unres <= '0; n_late <= '0; n_refused <= '0;
            ts_eof <= '0; ts_go <= '0; ts_sop <= '0; ts_rxsop <= '0; lat_last <= '0; lat_min <= 32'h7FFFFFFF; lat_max <= 32'h80000000; lat_cnt <= '0; lat_neg <= '0;
            for (int i = 0; i < 16; i++) hist[i] <= '0;
        end else begin
            if (s_v && s_eof) ts_eof <= ts;
            if (rx_sop) ts_rxsop <= ts;
            if (go) ts_go <= ts;
            if (ord_drop) n_drop <= n_drop + 32'd1;
            if (b_late) n_late <= n_late + 32'd1;
            if (refuse_v) n_refused <= n_refused + 32'd1;
            if (ord_end) begin
                if (ord_end_seg || ord_end_ofl) begin
                    if (ord_end_unres) n_unres <= n_unres + 32'd1; else n_pz_abort <= n_pz_abort + 32'd1;
                end else if (r_bad) n_pz_bad <= n_pz_bad + 32'd1;
                else if (k_strict && r_unk) n_pz_strict <= n_pz_strict + 32'd1;
                else begin n_sent <= n_sent + 32'd1; if (r_unk) n_unv <= n_unv + 32'd1; end
            end
            if (ord_sop) begin
                ts_sop <= ts; lat_last <= lat_v; lat_cnt <= lat_cnt + 32'd1;
                if (lat_v[31]) lat_neg <= lat_neg + 32'd1;
                else begin
                    if ($signed(lat_v) < $signed(lat_min)) lat_min <= lat_v;
                    if ($signed(lat_v) > $signed(lat_max)) lat_max <= lat_v;
                    if (hist[lat_bin] != 16'hFFFF) hist[lat_bin] <= hist[lat_bin] + 16'd1;
                end
            end
            if (c_cnt) begin
                n_sent <= '0; n_pz_abort <= '0; n_pz_bad <= '0; n_pz_strict <= '0; n_unv <= '0; n_drop <= '0; n_unres <= '0; n_late <= '0; n_refused <= '0;
            end
            if (c_lat || c_cnt) begin
                lat_min <= 32'h7FFFFFFF; lat_max <= 32'h80000000; lat_cnt <= '0; lat_neg <= '0;
                for (int i = 0; i < 16; i++) hist[i] <= '0;
            end
        end
    end

    // ---------------------------------------------------------------- STAT2
    logic [31:0] sw [NSW];
    always_comb begin
        for (int i = 0; i < NSW; i++) sw[i] = 32'd0;
        for (int i = 0; i < NC; i++) sw[S_ITCH + i] = cnt_i[32*i +: 32];
        for (int i = 0; i < 15; i++) sw[S_US + i] = cnt_us[32*i +: 32];
        sw[S_O_SENT] = n_sent; sw[S_O_PZ_ABORT] = n_pz_abort; sw[S_O_PZ_BAD] = n_pz_bad; sw[S_O_PZ_STRICT] = n_pz_strict; sw[S_O_UNV] = n_unv; sw[S_O_DROP] = n_drop;
        sw[S_O_OFL] = n_ofl; sw[S_O_UNRES] = n_unres; sw[S_O_LATE] = n_late;
        sw[S_RP_FRAMES] = rp_frames; sw[S_RP_STAT] = {rp_err[15:0], 7'd0, rp_busy, rpw_q};
        sw[S_LAT_LAST] = lat_last; sw[S_LAT_MIN] = lat_min; sw[S_LAT_MAX] = lat_max; sw[S_LAT_CNT] = lat_cnt; sw[S_LAT_NEG] = lat_neg;
        for (int i = 0; i < 8; i++) sw[S_HIST + i] = {hist[2*i+1], hist[2*i]};
        sw[S_TS_EOF] = ts_eof; sw[S_TS_GO] = ts_go; sw[S_TS_SOP] = ts_sop; sw[S_TS_RXSOP] = ts_rxsop;
        sw[S_FLAGS] = {12'd0, k_en, infl, ord_busy, rp_busy, flags};
        sw[S_CAP_LO] = cap_data[31:0]; sw[S_CAP_HI] = cap_data[63:32]; sw[S_CAP_ECHO] = {25'd0, cw[C_CAPADDR][6:0]};
        sw[S_TCPF_RD] = tcpf_rd; sw[S_TCPF_ECHO] = {24'd0, tcpf_q}; sw[S_CMD_ECHO] = {24'd0, cmd_seq_q}; sw[S_REFUSED] = n_refused;
    end
    always_comb for (int i = 0; i < NSW; i++) stat2[32*i +: 32] = sw[i];
    logic _unused;
    assign _unused = &{1'b0, rp_err[31:16], ord_end_fcs, k_kill == 1'b0 && 1'b0, commit, abort, go_spec, thr_b, qty_b, arm_b, kill_b, trade_en_b, gen_kind, gen_len, gen_inst, gen_price, gen_interval,
                       gen_count, port_feed, port_probe, cw[C_FEEDPORT][31:16]};
endmodule
