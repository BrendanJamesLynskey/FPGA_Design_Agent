// eth_mac_rgmii.sv: tri-mode (10/100/1000 Mb/s) Ethernet MAC for an RGMII PHY, our own (ip_lib).
//
// Receive: RGMII (rgmii_rx, in the RX_CLK domain) -> an asynchronous FIFO into clk (gmii_cdc) -> mac_rx.
//   The cut-through view is always there: every frame byte leaves on rx_* one clock after it reaches mac_rx, before
//   the FCS is known, and rx_end_* gives the verdict at the end (the trading path's speculative path).
//   CUT_THROUGH = 0 adds a store-and-forward buffer (eth_rx_sf): good frames only, FCS removed, on an AXI-Stream
//   master with back-pressure. With CUT_THROUGH = 1 that buffer is not built and m_axis is idle.
// Transmit: an AXI-Stream slave (tlast ends the frame; tuser on any beat, or poison, marks it bad) -> mac_tx ->
//   rgmii_tx. Once a frame has started its bytes must keep coming: a beat missing when the MAC needs it (an underrun)
//   ends the frame with a bad FCS (tx_underrun). The MAC pads to MIN_DATA and adds the FCS.
// speed: 2 = 1000, 1 = 100, 0 = 10 Mb/s, from the PHY's link status (management is outside this block); change it
// only while no frame is passing. clk is 125 MHz at every speed; clk90 is the same clock 90 degrees later.
// rx_clk must already be on a clock buffer (the board top's job); the PHY's RX delay mode is the board's choice.
//
// Version 0.2 adds, each off by default so that the defaults behave exactly as 0.1.0:
//   FILTER = 1  receive address filter (eth_rx_classify: own unicast, broadcast, promiscuous, multicast by an exact
//               table of MC_EXACT entries plus a 64-bin CRC hash). The cut-through view still carries every frame and
//               flags a rejected one with rx_end_filtered; the store-and-forward output drops it.
//   VLAN = 1    reports an 802.1Q/802.1ad tag (rx_end_vlan, rx_end_tci); VLAN = 2 also strips it from the
//               store-and-forward output and gives its TCI on m_axis_tci/m_axis_tagged.
//   PAUSE = 1   IEEE 802.3 annex 31B: a good pause frame received stops new transmit frames for quanta x 512 bit
//               times (a frame already started finishes); pause_req sends a pause frame with pause_quanta at the next
//               frame boundary, ahead of waiting data. MAC control frames (EtherType 0x8808) are consumed: they never
//               reach the store-and-forward output.
//   STATS = 1   the statistics counters of eth_mac_stats, read through stat_addr/stat_data.
//   MAX_FRAME up to 9216 (jumbo frames): rx_idx and rx_end_len widen from 11 to 14 bits when MAX_FRAME > 2000, and
//               SF_DEPTH must hold two such frames.
//   RX_RAM      the store-and-forward buffer in block RAM ("bram") or LUT RAM ("lutram"): the implementation variants.
//   IO_FAMILY   the DDR input and output registers: "ultrascale" (IDDRE1/ODDRE1, UltraScale and UltraScale+) or
//               "7series" (IDDR/ODDR).
// The new inputs (mac_addr and the filter, pause and statistics controls) must be tied when unused.

module eth_mac_rgmii #(
    parameter int CUT_THROUGH = 1,      // 1: cut-through only; 0: also the store-and-forward AXI-Stream output
    parameter int MIN_FRAME   = 64,     // receive: shortest good frame, FCS included
    parameter int MAX_FRAME   = 1522,   // receive: longest good frame, FCS included (up to 9216: jumbo frames)
    parameter int MIN_DATA    = 60,     // transmit: pad to this many bytes before the FCS
    parameter int IFG_BYTES   = 12,     // transmit: inter-frame gap in byte times
    parameter int SF_DEPTH    = 4096,   // store-and-forward buffer, bytes (CUT_THROUGH = 0)
    parameter int FILTER      = 0,      // 1: receive address filter
    parameter int MC_EXACT    = 4,      // exact-match multicast entries (FILTER = 1)
    parameter int VLAN        = 0,      // 0: none; 1: detect and report a tag; 2: also strip it (store-and-forward)
    parameter int PAUSE       = 0,      // 1: IEEE 802.3x pause, receive and transmit
    parameter int STATS       = 0,      // 1: statistics counters
    parameter int STAT_W      = 32,     // counter width (STATS = 1)
    parameter     RX_RAM      = "bram", // store-and-forward buffer: "bram" or "lutram"
    parameter     IO_FAMILY   = "ultrascale"    // "ultrascale" or "7series"
) (
    input  logic        clk,
    input  logic        clk90,
    input  logic        rst,
    input  logic [1:0]  speed,
    // RGMII
    input  logic        rgmii_rx_clk,
    input  logic [3:0]  rgmii_rxd,
    input  logic        rgmii_rx_ctl,
    output logic        rgmii_txc,
    output logic [3:0]  rgmii_txd,
    output logic        rgmii_tx_ctl,
    // receive, cut-through view
    output logic        rx_sof_pulse,   // the SFD reached mac_rx (timestamp point)
    output logic        rx_valid,
    output logic        rx_sof,
    output logic [7:0]  rx_data,
    output logic [((MAX_FRAME > 2000) ? 14 : 11)-1:0] rx_idx,
    output logic        rx_end_valid,
    output logic        rx_end_good,
    output logic        rx_end_fcs_err,
    output logic        rx_end_runt,
    output logic        rx_end_giant,
    output logic        rx_end_er,
    output logic [((MAX_FRAME > 2000) ? 14 : 11)-1:0] rx_end_len,
    output logic        rx_fifo_ovf,
    // receive classification, with rx_end_valid (0 when the feature is off)
    output logic        rx_da_valid,    // the destination address has been checked (from 2 clocks after byte 5)
    output logic        rx_da_match,    // with rx_da_valid: the filter accepts it (1 when FILTER = 0)
    output logic        rx_end_filtered,
    output logic        rx_end_bcast,
    output logic        rx_end_mcast,
    output logic        rx_end_vlan,
    output logic [15:0] rx_end_tci,
    output logic        rx_end_ctrl,
    output logic        rx_end_pause,
    // receive, store-and-forward (CUT_THROUGH = 0)
    output logic [7:0]  m_axis_tdata,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready,
    output logic        m_axis_tlast,
    output logic [15:0] m_axis_tci,     // VLAN = 2: the stripped tag's TCI, with every byte of the frame
    output logic        m_axis_tagged,
    output logic        rx_sf_dropped,
    output logic        rx_sf_overflow,
    // transmit
    input  logic [7:0]  s_axis_tdata,
    input  logic        s_axis_tvalid,
    output logic        s_axis_tready,
    input  logic        s_axis_tlast,
    input  logic        s_axis_tuser,
    input  logic        tx_poison,
    output logic        tx_first_pulse, // the first preamble byte is on the wire side of the MAC
    output logic        tx_sof_pulse,
    output logic        tx_last_pulse,
    output logic        tx_last_poisoned,
    output logic        tx_underrun,
    // station address, filter configuration (FILTER = 1; static while frames pass)
    input  logic [47:0] mac_addr,       // first byte on the wire in [47:40]
    input  logic        promisc,
    input  logic        bcast_en,
    input  logic        mcast_all,
    input  logic [63:0] mc_hash,
    input  logic        mc_we,
    input  logic [3:0]  mc_idx,
    input  logic [47:0] mc_addr,
    input  logic        mc_en,
    // pause (PAUSE = 1)
    input  logic        pause_req,      // one clock: send a pause frame with pause_quanta
    input  logic [15:0] pause_quanta,
    output logic        tx_paused,      // a received pause is holding new frames back
    output logic        tx_pause_sent,  // one clock, with tx_last_pulse of a pause frame
    // statistics (STATS = 1)
    input  logic        stat_clear,
    input  logic [4:0]  stat_addr,
    output logic [STAT_W-1:0] stat_data // one clock after stat_addr
);
    localparam int LW = (MAX_FRAME > 2000) ? 14 : 11;
    localparam int CLS = (FILTER != 0 || VLAN != 0 || PAUSE != 0 || STATS != 0) ? 1 : 0;
    initial begin
        if (CUT_THROUGH != 0 && CUT_THROUGH != 1) $error("eth_mac_rgmii: CUT_THROUGH must be 0 or 1 (got %0d)", CUT_THROUGH);
        if (MIN_FRAME < 18 || MIN_FRAME > MAX_FRAME) $error("eth_mac_rgmii: MIN_FRAME must be in 18..MAX_FRAME (got %0d)", MIN_FRAME);
        if (MAX_FRAME < 64 || MAX_FRAME > 9216) $error("eth_mac_rgmii: MAX_FRAME must be in 64..9216 (got %0d)", MAX_FRAME);
        if (CUT_THROUGH == 0 && SF_DEPTH < 2 * MAX_FRAME) $error("eth_mac_rgmii: SF_DEPTH must hold two frames of MAX_FRAME (got %0d)", SF_DEPTH);
        if (FILTER != 0 && FILTER != 1) $error("eth_mac_rgmii: FILTER must be 0 or 1 (got %0d)", FILTER);
        if (MC_EXACT < 0 || MC_EXACT > 16) $error("eth_mac_rgmii: MC_EXACT must be in 0..16 (got %0d)", MC_EXACT);
        if (VLAN < 0 || VLAN > 2) $error("eth_mac_rgmii: VLAN must be 0, 1 or 2 (got %0d)", VLAN);
        if (VLAN == 2 && CUT_THROUGH != 0) $error("eth_mac_rgmii: VLAN = 2 (strip) needs CUT_THROUGH = 0");
        if (PAUSE != 0 && PAUSE != 1) $error("eth_mac_rgmii: PAUSE must be 0 or 1 (got %0d)", PAUSE);
        if (PAUSE != 0 && MIN_DATA > 60) $error("eth_mac_rgmii: PAUSE needs MIN_DATA <= 60 (got %0d)", MIN_DATA);
        if (STATS != 0 && STATS != 1) $error("eth_mac_rgmii: STATS must be 0 or 1 (got %0d)", STATS);
        if (STAT_W < 16 || STAT_W > 64) $error("eth_mac_rgmii: STAT_W must be in 16..64 (got %0d)", STAT_W);
        if (RX_RAM != "bram" && RX_RAM != "lutram") $error("eth_mac_rgmii: RX_RAM must be \"bram\" or \"lutram\"");
        if (IO_FAMILY != "ultrascale" && IO_FAMILY != "7series") $error("eth_mac_rgmii: IO_FAMILY must be \"ultrascale\" or \"7series\"");
    end

    // ---- receive ----
    logic       rx_rst;
    xpm_cdc_sync_rst #(.DEST_SYNC_FF(4), .INIT(1), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0)) u_rxrst (
        .src_rst(rst), .dest_clk(rgmii_rx_clk), .dest_rst(rx_rst));
    logic [1:0] speed_rx;
    xpm_cdc_array_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(1), .WIDTH(2)) u_spd (
        .src_clk(clk), .src_in(speed), .dest_clk(rgmii_rx_clk), .dest_out(speed_rx));
    logic [7:0] g_d;
    logic       g_v, g_dv, g_er;
    rgmii_rx #(.FAMILY(IO_FAMILY)) u_rgrx (.rx_clk(rgmii_rx_clk), .speed(speed_rx), .rxd(rgmii_rxd), .rx_ctl(rgmii_rx_ctl),
                     .gmii_d(g_d), .gmii_v(g_v), .gmii_dv(g_dv), .gmii_er(g_er));
    logic       f_v, f_eof, f_er;
    logic [7:0] f_d;
    gmii_cdc u_cdc (.rx_clk(rgmii_rx_clk), .rx_rst(rx_rst), .gmii_d(g_d), .gmii_v(g_v), .gmii_dv(g_dv), .gmii_er(g_er),
                    .clk, .o_v(f_v), .o_eof(f_eof), .o_er(f_er), .o_d(f_d), .o_ovf(rx_fifo_ovf), .o_rxclk_cnt());
    mac_rx #(.MIN_FRAME(MIN_FRAME), .MAX_FRAME(MAX_FRAME), .LEN_W(LW)) u_rx (.clk, .rst, .in_valid(f_v), .in_eof(f_eof),
        .in_er(f_er), .in_data(f_d), .sof_pulse(rx_sof_pulse), .out_valid(rx_valid), .out_sof(rx_sof),
        .out_data(rx_data), .out_idx(rx_idx), .end_valid(rx_end_valid), .end_good(rx_end_good),
        .end_fcs_err(rx_end_fcs_err), .end_runt(rx_end_runt), .end_giant(rx_end_giant), .end_er(rx_end_er),
        .end_len(rx_end_len), .ev_bad_pre());

    // classification: address filter, VLAN tag, MAC control and pause frames
    logic c_dav, c_match, c_own, c_bcast, c_mcast, c_vlan, c_ctrl, c_pause;
    logic [15:0] c_tci, c_quanta;
    if (CLS != 0) begin : g_cls
        eth_rx_classify #(.MC_EXACT(MC_EXACT)) u_cls (.clk, .rst, .in_valid(rx_valid), .in_sof(rx_sof), .in_data(rx_data),
            .own_mac(mac_addr), .promisc, .bcast_en, .mcast_all, .mc_hash, .mc_we, .mc_idx, .mc_addr, .mc_en,
            .da_valid(c_dav), .match(c_match), .is_own(c_own), .is_bcast(c_bcast), .is_mcast(c_mcast),
            .is_vlan(c_vlan), .tci(c_tci), .is_ctrl(c_ctrl), .is_pause(c_pause), .quanta(c_quanta));
    end else begin : g_nocls
        assign c_dav = 1'b0; assign c_match = 1'b0; assign c_own = 1'b0; assign c_bcast = 1'b0; assign c_mcast = 1'b0;
        assign c_vlan = 1'b0; assign c_tci = '0; assign c_ctrl = 1'b0; assign c_pause = 1'b0; assign c_quanta = '0;
    end
    logic filtered, consumed;
    assign filtered        = (FILTER != 0) && !c_match;
    assign consumed        = (PAUSE != 0) && c_ctrl;
    assign rx_da_valid     = c_dav;
    assign rx_da_match     = (FILTER != 0) ? c_match : 1'b1;
    assign rx_end_filtered = filtered;
    assign rx_end_bcast    = c_bcast;
    assign rx_end_mcast    = c_mcast && !c_bcast;
    assign rx_end_vlan     = (VLAN != 0) && c_vlan;
    assign rx_end_tci      = (VLAN != 0) ? c_tci : 16'h0000;
    assign rx_end_ctrl     = c_ctrl;
    assign rx_end_pause    = (PAUSE != 0) && c_pause;

    if (CUT_THROUGH == 0) begin : g_sf
        eth_rx_sf #(.DEPTH(SF_DEPTH), .LEN_W(LW), .STRIP(VLAN == 2 ? 1 : 0), .RAM(RX_RAM)) u_sf (.clk, .rst,
            .in_valid(rx_valid), .in_sof(rx_sof), .in_data(rx_data), .end_valid(rx_end_valid), .end_good(rx_end_good),
            .end_keep(!filtered && !consumed), .end_len(rx_end_len), .m_axis_tdata, .m_axis_tvalid, .m_axis_tready,
            .m_axis_tlast, .m_axis_tci, .m_axis_tagged, .ev_dropped(rx_sf_dropped), .ev_overflow(rx_sf_overflow));
    end else begin : g_ct
        assign m_axis_tdata = '0; assign m_axis_tvalid = 1'b0; assign m_axis_tlast = 1'b0;
        assign m_axis_tci = '0; assign m_axis_tagged = 1'b0;
        assign rx_sf_dropped = 1'b0; assign rx_sf_overflow = 1'b0;
    end

    // ---- transmit ----
    logic          ce, ready, req_valid, last_pulse;
    logic [LW-1:0] req_idx;
    logic [7:0]    t_d, g_txd;
    logic          t_last, bad, g_txen;
    // pause: the receive timer (byte times), the pending request and the source of the current frame
    logic [21:0]   ptimer;
    logic          pend_p, src_p;
    logic [15:0]   pq;
    logic          want_p, want_u, start;
    assign tx_paused = (PAUSE != 0) && ptimer != '0;
    assign want_p    = (PAUSE != 0) && pend_p;
    assign want_u    = s_axis_tvalid && !bad && !tx_paused;
    assign start     = want_p || want_u;
    always_ff @(posedge clk) begin
        if (rst || PAUSE == 0) begin ptimer <= '0; pend_p <= 1'b0; src_p <= 1'b0; pq <= '0; end
        else begin
            if (rx_end_valid && rx_end_good && c_pause) ptimer <= {c_quanta, 6'd0};        // quanta x 64 byte times
            else if (ce && ptimer != '0) ptimer <= ptimer - 22'd1;
            if (ce && ready && start) begin
                src_p <= want_p;
                if (want_p) pend_p <= 1'b0;
            end
            if (pause_req) begin pend_p <= 1'b1; pq <= pause_quanta; end
        end
    end
    // the pause frame (annex 31B): 01-80-C2-00-00-01, own address, 0x8808, opcode 0x0001, quanta, zeros to 60 bytes
    function automatic logic [7:0] pbyte(input logic [LW-1:0] i, input logic [47:0] sa, input logic [15:0] q);
        case (int'(i))
            0: pbyte = 8'h01; 1: pbyte = 8'h80; 2: pbyte = 8'hC2; 3: pbyte = 8'h00; 4: pbyte = 8'h00; 5: pbyte = 8'h01;
            6: pbyte = sa[47:40]; 7: pbyte = sa[39:32]; 8: pbyte = sa[31:24]; 9: pbyte = sa[23:16]; 10: pbyte = sa[15:8];
            11: pbyte = sa[7:0]; 12: pbyte = 8'h88; 13: pbyte = 8'h08; 14: pbyte = 8'h00; 15: pbyte = 8'h01;
            16: pbyte = q[15:8]; 17: pbyte = q[7:0];
            default: pbyte = 8'h00;
        endcase
    endfunction

    // one beat is taken at each byte time the MAC asks for one; a missing beat is an underrun
    assign s_axis_tready = ce && req_valid && !bad && !src_p;
    always_ff @(posedge clk) begin
        tx_underrun <= 1'b0;
        if (rst) begin t_d <= '0; t_last <= 1'b0; bad <= 1'b0; end
        else begin
            if (ce && req_valid) begin
                if (src_p) begin t_d <= pbyte(req_idx, mac_addr, pq); t_last <= (req_idx == LW'(59)); end
                else if (bad) begin t_d <= 8'h00; t_last <= 1'b1; end
                else if (s_axis_tvalid) begin
                    t_d <= s_axis_tdata; t_last <= s_axis_tlast;
                    if (s_axis_tuser) bad <= 1'b1;
                end else begin
                    t_d <= 8'h00; t_last <= 1'b1; bad <= 1'b1; tx_underrun <= 1'b1;
                end
            end
            if (last_pulse) bad <= 1'b0;
        end
    end
    mac_tx #(.MIN_DATA(MIN_DATA), .IFG_BYTES(IFG_BYTES), .LEN_W(LW)) u_tx (.clk, .rst, .ce, .start,
        .ready, .req_idx, .req_valid, .in_data(t_d), .in_last(t_last), .poison((tx_poison && !src_p) || bad), .txd(g_txd),
        .tx_en(g_txen), .first_pulse(tx_first_pulse), .sof_pulse(tx_sof_pulse), .last_pulse(last_pulse),
        .last_poisoned(tx_last_poisoned), .busy());
    assign tx_last_pulse = last_pulse;
    assign tx_pause_sent = last_pulse && src_p;
    rgmii_tx #(.FAMILY(IO_FAMILY)) u_rgtx (.clk, .clk90, .rst, .speed, .ce, .gmii_d(g_txd), .gmii_en(g_txen), .gmii_er(1'b0),
                     .txd(rgmii_txd), .tx_ctl(rgmii_tx_ctl), .txc(rgmii_txc));

    // ---- statistics ----
    if (STATS != 0) begin : g_stats
        // transmit frame summary: beats taken, the destination's group bit and whether it is all ones
        logic [LW-1:0] tn;
        logic          t_g, t_ones;
        always_ff @(posedge clk) begin
            if (rst || (ce && ready && start)) begin tn <= '0; t_g <= 1'b0; t_ones <= 1'b1; end
            else if (s_axis_tvalid && s_axis_tready) begin
                if (tn != '1) tn <= tn + 1'b1;
                if (tn == '0) t_g <= s_axis_tdata[0];
                if (tn < LW'(6) && s_axis_tdata != 8'hFF) t_ones <= 1'b0;
            end
        end
        logic [LW-1:0] t_len;
        assign t_len = src_p ? LW'(64) : ((tn > LW'(MIN_DATA)) ? tn : LW'(MIN_DATA)) + LW'(4);
        eth_mac_stats #(.STAT_W(STAT_W), .LEN_W(LW)) u_stats (.clk, .rst, .clear(stat_clear),
            .rx_ev(rx_end_valid), .rx_len(rx_end_len), .rx_good(rx_end_good), .rx_fcs_err(rx_end_fcs_err),
            .rx_runt(rx_end_runt), .rx_giant(rx_end_giant), .rx_phy_err(rx_end_er), .rx_bcast(c_bcast),
            .rx_mcast(c_mcast), .rx_pause(rx_end_pause), .rx_vlan(c_vlan), .rx_filtered(filtered),
            .rx_dropped(rx_sf_overflow), .rx_fifo_ovf(rx_fifo_ovf),
            .tx_ev(last_pulse), .tx_len(t_len), .tx_good(!tx_last_poisoned), .tx_bcast(!src_p && t_ones && tn >= LW'(6)),
            .tx_mcast(src_p || t_g), .tx_pause(src_p), .tx_underrun(tx_underrun),
            .rd_addr(stat_addr), .rd_data(stat_data));
    end else begin : g_nostats
        assign stat_data = '0;
    end
endmodule
