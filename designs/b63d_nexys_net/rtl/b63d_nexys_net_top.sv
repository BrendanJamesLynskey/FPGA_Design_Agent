// b63d_nexys_net_top.sv: the library's network blocks on the Nexys A7-100T, behind the board's RMII PHY (LAN8720A).
//
// The library entries in the receive and transmit paths:
//   eth_mac_rmii (10/100 MAC) -> eth_rx_classify (the address filter of eth_mac_rgmii 0.2: own MAC, broadcast,
//   the two IGMP groups' multicast MACs by its exact table, promiscuous) -> arp_responder, icmp_echo, ipv4_udp_rx,
//   igmp_join; a frame the filter rejects reaches them with tuser set (they drop it).
//   Transmit: arp_responder, icmp_echo, igmp_join, ipv4_udp_tx and a host frame injector -> a frame arbiter ->
//   eth_mac_rmii. eth_mac_stats counts both directions; mdio_master reaches the PHY's registers.
//   A UDP service: any good datagram to UDP_PORT is answered (to the sender's address and port, the sender's MAC
//   from the ARP cache) with "N63D" and the 21 statistics counters, big-endian. A cache miss sends an ARP request
//   and drops the datagram (the sender retries).
//   A frame capture (2 KB) records one received frame (after `skip` others) for the host, and the injector sends a
//   frame the host wrote: with the PHY in loopback (MDIO, BMCR bit 14) the stack can be checked without a cable.
// Clocks: CLK100MHZ -> MMCM -> 50 MHz for all logic, and ETH_REFCLK (the PHY's reference clock in REF_CLK-in mode)
// through an ODDR from a second MMCM output at 335.25 degrees (1.375 ns before the logic clock's edge). The phase was
// chosen from Vivado's timing of the RMII pins against the forwarded clock: at the board manual's 45 degrees the clock
// reaches the PHY so late (MMCM, BUFG, ODDR, output buffer) that receive data missed setup by 2.3 ns with 5.5 ns of hold
// to spare; 335.25 degrees moves the PHY's clock earlier by 3.875 ns to centre the receive window. Simulation divides
// CLK100MHZ by two instead.
// Window registers (address = ADDR - 0x80), 32 bit:
//   0x00 CTRL      RW  [0] promisc, [1] bcast_en (1), [2] mcast_all, [3] PHY reset (ETH_RSTN low), [4] 100 Mb/s (1)
//   0x01 MAC_HI    RW  [15:0] own MAC bytes 0-1 (reset 0x0200)        0x02 MAC_LO  RW  bytes 2-5 (0x00000063)
//   0x03 IP        RW  own IPv4 (reset 192.168.63.2)                  0x04 MDIO    W: [30] read, [25:21] PHY, [20:16]
//                      register, [15:0] data, starts an access; R: [31] busy, [15:0] the value read
//   0x05 GROUP0, 0x06 GROUP1   RW  IGMP groups (239.63.0.1, 239.63.0.2)   0x07 GROUP_EN RW [1:0]
//   0x08 UDP_PORT  RW  the statistics service's port (5000)           0x09 STAT_CLEAR W: zeroes the counters
//   0x10-0x24      R   the 21 statistics counters of eth_mac_stats (its address order)
//   0x30 EV0 {ARP requests for us, ARP replies sent}  0x31 EV1 {echo requests, echo replies}
//   0x32 EV2 {UDP datagrams passed, UDP discarded}    0x33 EV3 {IGMP queries, IGMP reports and leaves sent}
//   0x34 EV4 {service replies, service ARP misses}    0x35 EV5 {0, ARP address conflicts}   (16 bits each, wrapping)
//   0x38-0x3B      R   raw XADC codes: Tj, VCCINT, VCCAUX, VCCBRAM (UG480)
//   0x3C ALARMS    R   latched XADC alarms since the last clear: [0] Tj, [1] VCCINT, [2] VCCAUX, [3] VCCBRAM, [4] OT;
//                      W: any value clears them
//   0x40 INJ_CTRL  W: [10:0] length, [31] send; R: [31] busy      0x41 INJ_DATA W: 4 bytes (first in [31:24]) at the
//   word pointer, which then advances     0x42 INJ_PTR W: the word pointer
//   0x48 CAP_CTRL  W: [0] arm, [7:4] frames to skip; R: [31] done, [30] the frame's tuser, [10:0] length
//   0x49 CAP_ADDR  W: byte index          0x4A CAP_DATA R: [7:0] that byte; the index advances
/* verilator lint_off UNUSEDSIGNAL */
module b63d_nexys_net_top #(
    parameter int          CLKS_PER_BIT   = 434,          // 115200 baud at 50 MHz
    parameter int          TIMEOUT_CYCLES = 50_000,
    parameter int          TICK_CLKS      = 5_000_000,    // 0.1 s at 50 MHz (IGMP timers)
    parameter int          ARP_HOLDOFF    = 16_000_000,   // 0.32 s
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic       CLK100MHZ,
    input  logic       CPU_RESETN,
    input  logic       UART_TXD_IN,
    output logic       UART_RXD_OUT,
    output logic       ETH_MDC,
    inout  wire        ETH_MDIO,
    output logic       ETH_RSTN,
    input  logic       ETH_CRSDV,
    input  logic       ETH_RXERR,
    input  logic [1:0] ETH_RXD,
    output logic       ETH_TXEN,
    output logic [1:0] ETH_TXD,
    output logic       ETH_REFCLK,
    output logic [3:0] LED
);
    // ------------------------------------------------------------------ clocks and reset
    logic clk, locked;
`ifdef SYNTHESIS
    logic fb, c0, c1, clk45;
    MMCME2_BASE #(.CLKIN1_PERIOD(10.0), .CLKFBOUT_MULT_F(10.0), .DIVCLK_DIVIDE(1), .CLKOUT0_DIVIDE_F(20.0),
                  .CLKOUT1_DIVIDE(20), .CLKOUT1_PHASE(335.25)) u_mmcm (
        .CLKIN1(CLK100MHZ), .CLKFBIN(fb), .CLKFBOUT(fb), .CLKOUT0(c0), .CLKOUT1(c1), .LOCKED(locked), .RST(1'b0),
        .PWRDWN(1'b0), .CLKFBOUTB(), .CLKOUT0B(), .CLKOUT1B(), .CLKOUT2(), .CLKOUT2B(), .CLKOUT3(), .CLKOUT3B(),
        .CLKOUT4(), .CLKOUT5(), .CLKOUT6());
    BUFG u_bg0 (.I(c0), .O(clk));
    BUFG u_bg1 (.I(c1), .O(clk45));
    ODDR #(.DDR_CLK_EDGE("SAME_EDGE"), .INIT(1'b0), .SRTYPE("SYNC")) u_refclk (.Q(ETH_REFCLK), .C(clk45), .CE(1'b1),
        .D1(1'b1), .D2(1'b0), .R(1'b0), .S(1'b0));
`else
    logic div2 = 1'b0;
    always_ff @(posedge CLK100MHZ) div2 <= !div2;
    assign clk = div2;
    assign locked = 1'b1;
    assign ETH_REFCLK = clk;
`endif
    // the button and the MMCM's lock each through their own synchroniser (no logic before either), then combined
    logic rst, rst_btn, rst_lk;
    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst_btn));
    reset_sync u_rlk (.clk(clk), .rst_n_async(locked), .rst(rst_lk));
    always_ff @(posedge clk) rst <= rst_btn || rst_lk;

    // ------------------------------------------------------------------ the test shell and its registers
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;
    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES), .DESIGN_ID(32'h4E36_3344),
                 .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    logic        promisc, bcast_en, mcast_all, phy_rst, speed_100, stat_clear;
    logic [47:0] own_mac;
    logic [31:0] own_ip, grp0, grp1;
    logic [1:0]  group_en;
    logic [15:0] udp_port;
    always_ff @(posedge clk) begin
        stat_clear <= 1'b0;
        if (rst) begin
            promisc <= 1'b0; bcast_en <= 1'b1; mcast_all <= 1'b0; phy_rst <= 1'b0; speed_100 <= 1'b1;
            own_mac <= 48'h0200_0000_0063; own_ip <= 32'hC0A8_3F02; grp0 <= 32'hEF3F_0001; grp1 <= 32'hEF3F_0002;
            group_en <= 2'b00; udp_port <= 16'd5000;
        end else if (win_wr) begin
            case (win_addr)
                7'h00: begin promisc <= win_wdata[0]; bcast_en <= win_wdata[1]; mcast_all <= win_wdata[2];
                             phy_rst <= win_wdata[3]; speed_100 <= win_wdata[4]; end
                7'h01: own_mac[47:32] <= win_wdata[15:0];
                7'h02: own_mac[31:0]  <= win_wdata;
                7'h03: own_ip   <= win_wdata;
                7'h05: grp0     <= win_wdata;
                7'h06: grp1     <= win_wdata;
                7'h07: group_en <= win_wdata[1:0];
                7'h08: udp_port <= win_wdata[15:0];
                7'h09: stat_clear <= 1'b1;
                default: ;
            endcase
        end
    end
    assign ETH_RSTN = !phy_rst;

    // ------------------------------------------------------------------ MDIO
    logic        md_busy, mdc, md_o, md_t, md_i;
    logic [15:0] md_rdata;
    (* ASYNC_REG = "TRUE" *) logic [1:0] md_sync;
    always_ff @(posedge clk) md_sync <= {md_sync[0], ETH_MDIO};
    assign md_i = md_sync[1];
    mdio_master #(.DIV(13)) u_mdio (.clk, .rst, .go(win_wr && win_addr == 7'h04), .rd(win_wdata[30]),
        .phy(win_wdata[25:21]), .reg_a(win_wdata[20:16]), .wdata(win_wdata[15:0]), .rdata(md_rdata), .busy(md_busy),
        .mdc(mdc), .mdio_o(md_o), .mdio_t(md_t), .mdio_i(md_i));
    assign ETH_MDC  = mdc;
    assign ETH_MDIO = md_t ? 1'bz : md_o;

    // ------------------------------------------------------------------ the MAC
    logic [7:0] rx_d, tx_d;
    logic       rx_v, rx_l, rx_u, tx_v, tx_r, tx_l;
    logic       ev_rx_ok, ev_rx_bad, ev_rx_fcs, ev_rx_runt, ev_tx_sent, ev_tx_underrun;
    // transmit pins from falling-edge registers: the data change half a clock after the logic clock's edge, which keeps
    // them clear of the PHY's sampling edge (its REF_CLK reaches it several ns after the logic clock, see above) with
    // margin for both setup and hold (the timing report in results/b63d gives the slack)
    logic       mac_txen;
    logic [1:0] mac_txd;
    always_ff @(negedge clk) begin ETH_TXEN <= mac_txen; ETH_TXD <= mac_txd; end
    eth_mac_rmii #(.MIN_FRAME(64), .MIN_DATA(60), .IFG_BYTES(12)) u_mac (.clk, .rst, .speed_100(speed_100),
        .rmii_crs_dv(ETH_CRSDV), .rmii_rxd(ETH_RXD), .rmii_rx_er(ETH_RXERR), .rmii_tx_en(mac_txen), .rmii_txd(mac_txd),
        .rx_axis_tdata(rx_d), .rx_axis_tvalid(rx_v), .rx_axis_tlast(rx_l), .rx_axis_tuser(rx_u),
        .tx_axis_tdata(tx_d), .tx_axis_tvalid(tx_v), .tx_axis_tready(tx_r), .tx_axis_tlast(tx_l), .tx_axis_tuser(1'b0),
        .ev_rx_ok(ev_rx_ok), .ev_rx_bad(ev_rx_bad), .ev_rx_fcs_err(ev_rx_fcs), .ev_rx_runt(ev_rx_runt),
        .ev_tx_sent(ev_tx_sent), .ev_tx_underrun(ev_tx_underrun));

    // ------------------------------------------------------------------ receive: the address filter
    logic in_frame, rx_sof;
    always_ff @(posedge clk) begin
        if (rst) in_frame <= 1'b0;
        else if (rx_v) in_frame <= !rx_l;
    end
    assign rx_sof = rx_v && !in_frame;
    logic        c_dav, c_match, c_own, c_bcast, c_mcast, c_vlan, c_ctrl, c_pause;
    logic [15:0] c_tci, c_quanta;
    logic        mc_sel;
    always_ff @(posedge clk) mc_sel <= !mc_sel;            // the two exact entries are kept equal to the groups' MACs
    logic [31:0] mc_g;
    assign mc_g = mc_sel ? grp1 : grp0;
    eth_rx_classify #(.MC_EXACT(2)) u_cls (.clk, .rst, .in_valid(rx_v), .in_sof(rx_sof), .in_data(rx_d),
        .own_mac(own_mac), .promisc(promisc), .bcast_en(bcast_en), .mcast_all(mcast_all), .mc_hash(64'd0),
        .mc_we(1'b1), .mc_idx({3'd0, mc_sel}), .mc_addr({24'h01005E, 1'b0, mc_g[22:0]}), .mc_en(group_en[mc_sel]),
        .da_valid(c_dav), .match(c_match), .is_own(c_own), .is_bcast(c_bcast), .is_mcast(c_mcast), .is_vlan(c_vlan),
        .tci(c_tci), .is_ctrl(c_ctrl), .is_pause(c_pause), .quanta(c_quanta));
    logic rx_uf;                                            // tuser after the filter
    assign rx_uf = rx_u || (rx_l && !(c_dav && c_match));

    // ------------------------------------------------------------------ protocol blocks
    logic [7:0]  a_d, i_d, g_d, u_d, j_d;
    logic        a_v, a_r, a_l, i_v, i_r, i_l, g_v, g_r, g_l, u_v, u_r, u_l, j_v, j_r, j_l;
    logic        lk_valid, lk_done, lk_hit;
    logic [31:0] lk_ip;
    logic [47:0] lk_mac;
    logic        e_arp_req, e_arp_rep, e_arp_tx_rep, e_arp_tx_req, e_arp_learn, e_arp_drop, e_arp_conflict;
    arp_responder #(.CACHE_N(4), .HOLDOFF(ARP_HOLDOFF)) u_arp (.clk, .rst, .own_mac, .own_ip,
        .s_axis_tdata(rx_d), .s_axis_tvalid(rx_v), .s_axis_tready(), .s_axis_tlast(rx_l), .s_axis_tuser(rx_uf),
        .m_axis_tdata(a_d), .m_axis_tvalid(a_v), .m_axis_tready(a_r), .m_axis_tlast(a_l),
        .lk_valid, .lk_ip, .lk_ready(), .lk_done, .lk_hit, .lk_mac, .flush(1'b0),
        .ev_rx_request(e_arp_req), .ev_rx_reply(e_arp_rep), .ev_tx_reply(e_arp_tx_rep), .ev_tx_request(e_arp_tx_req),
        .ev_learn(e_arp_learn), .ev_drop(e_arp_drop), .ev_conflict(e_arp_conflict));
    logic e_ping, e_pong, e_ping_busy, e_ping_bad;
    icmp_echo #(.BUF_BYTES(2048), .TTL(64), .RAM("bram")) u_icmp (.clk, .rst, .own_mac, .own_ip,
        .s_axis_tdata(rx_d), .s_axis_tvalid(rx_v), .s_axis_tready(), .s_axis_tlast(rx_l), .s_axis_tuser(rx_uf),
        .m_axis_tdata(i_d), .m_axis_tvalid(i_v), .m_axis_tready(i_r), .m_axis_tlast(i_l),
        .ev_request(e_ping), .ev_reply(e_pong), .ev_busy(e_ping_busy), .ev_bad(e_ping_bad));
    logic e_query, e_report, e_leave, e_supp;
    igmp_join #(.N_GROUPS(2), .TICK_CLKS(TICK_CLKS), .UNSOL_TICKS(10)) u_igmp (.clk, .rst, .own_mac, .own_ip,
        .groups({grp1, grp0}), .group_en, .s_axis_tdata(rx_d), .s_axis_tvalid(rx_v), .s_axis_tready(),
        .s_axis_tlast(rx_l), .s_axis_tuser(rx_uf), .m_axis_tdata(g_d), .m_axis_tvalid(g_v), .m_axis_tready(g_r),
        .m_axis_tlast(g_l), .ev_query(e_query), .ev_report(e_report), .ev_leave(e_leave), .ev_suppressed(e_supp));
    // UDP receive: the service port only; its output is always taken
    logic [7:0]  ur_d;
    logic        ur_v, ur_l, ur_u;
    logic [2:0]  ur_dest;
    logic [31:0] ur_sip, ur_dip;
    logic [15:0] ur_sport, ur_dport, ur_len;
    logic        e_u_ok, e_u_badip, e_u_bad, e_u_noport, e_u_frag, e_u_empty;
    ipv4_udp_rx #(.N_PORTS(1), .CHECK_UDP(1), .ACCEPT_BCAST(1), .ACCEPT_MCAST(1)) u_udprx (.clk, .rst, .own_ip,
        .ports(udp_port), .port_en(1'b1), .s_axis_tdata(rx_d), .s_axis_tvalid(rx_v), .s_axis_tready(),
        .s_axis_tlast(rx_l), .s_axis_tuser(rx_uf), .m_axis_tdata(ur_d), .m_axis_tvalid(ur_v), .m_axis_tready(1'b1),
        .m_axis_tlast(ur_l), .m_axis_tuser(ur_u), .m_axis_tdest(ur_dest), .m_src_ip(ur_sip), .m_dst_ip(ur_dip),
        .m_src_port(ur_sport), .m_dst_port(ur_dport), .m_len(ur_len), .ev_ok(e_u_ok), .ev_bad_ip(e_u_badip),
        .ev_bad_udp(e_u_bad), .ev_no_port(e_u_noport), .ev_frag(e_u_frag), .ev_empty(e_u_empty));

    // ------------------------------------------------------------------ statistics (both directions)
    logic [4:0]  st_addr;
    logic [31:0] st_data;
    logic [10:0] rx_n, tx_n;
    logic        tx_g, tx_ones;
    logic        rx_ev;
    logic [10:0] rx_len;
    always_ff @(posedge clk) begin
        if (rst) begin rx_n <= '0; tx_n <= '0; tx_g <= 1'b0; tx_ones <= 1'b1; end
        else begin
            if (rx_v) rx_n <= rx_l ? 11'd0 : rx_n + 11'd1;
            if (tx_v && tx_r) begin
                tx_n <= tx_l ? 11'd0 : tx_n + 11'd1;
                if (tx_n == 11'd0) tx_g <= tx_d[0];
                if (tx_n < 11'd6 && tx_d != 8'hFF) tx_ones <= 1'b0;
                if (tx_l) tx_ones <= 1'b1;
            end
        end
    end
    assign rx_ev  = rx_v && rx_l;
    assign rx_len = rx_n + 11'd5;                           // the bytes before this one, this one, and the FCS
    logic [10:0] tx_len;
    assign tx_len = ((tx_n + 11'd1 > 11'd60) ? tx_n + 11'd1 : 11'd60) + 11'd4;
    eth_mac_stats #(.STAT_W(32), .LEN_W(11)) u_stats (.clk, .rst, .clear(stat_clear),
        .rx_ev(rx_ev), .rx_len(rx_len), .rx_good(!rx_u), .rx_fcs_err(ev_rx_fcs), .rx_runt(ev_rx_runt),
        .rx_giant(1'b0), .rx_phy_err(1'b0), .rx_bcast(c_bcast), .rx_mcast(c_mcast), .rx_pause(c_pause),
        .rx_vlan(c_vlan), .rx_filtered(!(c_dav && c_match)), .rx_dropped(1'b0), .rx_fifo_ovf(1'b0),
        .tx_ev(tx_v && tx_r && tx_l), .tx_len(tx_len), .tx_good(1'b1), .tx_bcast(tx_ones),
        .tx_mcast(tx_g), .tx_pause(1'b0), .tx_underrun(ev_tx_underrun), .rd_addr(st_addr), .rd_data(st_data));

    // ------------------------------------------------------------------ the UDP statistics service
    // A good datagram to the port: look the sender up; on a hit send "N63D" and the counters to it.
    localparam logic [1:0] V_IDLE = 2'd0, V_LOOK = 2'd1, V_WAIT = 2'd2, V_SEND = 2'd3;
    logic [1:0]  v_st;
    logic [31:0] v_ip;
    logic [15:0] v_port;
    logic [47:0] v_mac;
    logic [6:0]  v_i;                                       // payload byte index, 0..87
    logic [31:0] v_word;
    logic        v_need, win_rd_q, port_free;
    logic [15:0] n_svc, n_miss;
    assign port_free = !win_rd && !win_rd_q;                // a shell read of the counters is not using the port
    assign lk_valid  = (v_st == V_LOOK);
    assign lk_ip     = v_ip;
    always_ff @(posedge clk) begin
        win_rd_q <= win_rd;
        if (rst) begin v_st <= V_IDLE; v_ip <= '0; v_port <= '0; v_mac <= '0; n_svc <= '0; n_miss <= '0; end
        else case (v_st)
            V_IDLE: if (ur_v && ur_l && !ur_u) begin v_st <= V_LOOK; v_ip <= ur_sip; v_port <= ur_sport; end
            V_LOOK: v_st <= V_WAIT;
            V_WAIT: if (lk_done) begin
                        if (lk_hit) begin v_st <= V_SEND; v_mac <= lk_mac; n_svc <= n_svc + 16'd1; end
                        else begin v_st <= V_IDLE; n_miss <= n_miss + 16'd1; end
                    end
            default: if (u_v && u_r && u_l) v_st <= V_IDLE;    // V_SEND: until the reply's frame has left
        endcase
    end
    // the payload into ipv4_udp_tx: word w = "N63D" or counter w-1, read from the statistics port one word ahead
    logic [7:0] p_d;
    logic       p_v, p_r, p_l, p_load;
    logic [4:0] p_w;                                        // word being sent
    always_ff @(posedge clk) begin
        if (rst || v_st != V_SEND) begin v_i <= '0; p_w <= '0; v_word <= 32'h4E36_3344; v_need <= 1'b0; p_load <= 1'b0; end
        else begin
            p_load <= 1'b0;
            if (p_v && p_r) begin
                v_i <= v_i + 7'd1;
                if (v_i[1:0] == 2'd3) begin p_w <= p_w + 5'd1; v_need <= 1'b1; end
            end
            if (v_need && port_free && !p_load) begin p_load <= 1'b1; end
            if (p_load) begin v_word <= st_data; v_need <= 1'b0; end
        end
    end
    logic u_st_busy;                                        // the payload has been handed over: wait for the frame
    assign st_addr = (v_st == V_SEND && v_need && port_free) ? (p_w - 5'd1) : (win_addr[4:0] - 5'h10);
    assign p_v = (v_st == V_SEND) && !v_need && !p_load && v_i < 7'd88 && !u_st_busy;
    assign p_d = v_word[8 * (3 - int'(v_i[1:0])) +: 8];
    assign p_l = (v_i == 7'd87);
    always_ff @(posedge clk) begin
        if (rst || v_st != V_SEND) u_st_busy <= 1'b0;
        else if (p_v && p_r && p_l) u_st_busy <= 1'b1;
    end
    logic e_u_sent, e_u_long;
    ipv4_udp_tx #(.MAX_PAYLOAD(1472), .CSUM(1), .TTL(64), .RAM("bram")) u_udptx (.clk, .rst, .own_mac, .own_ip,
        .s_axis_tdata(p_d), .s_axis_tvalid(p_v), .s_axis_tready(p_r), .s_axis_tlast(p_l), .s_dst_mac(v_mac),
        .s_dst_ip(v_ip), .s_src_port(udp_port), .s_dst_port(v_port), .m_axis_tdata(u_d), .m_axis_tvalid(u_v),
        .m_axis_tready(u_r), .m_axis_tlast(u_l), .ev_sent(e_u_sent), .ev_too_long(e_u_long));

    // ------------------------------------------------------------------ the host's frame injector
    logic [31:0] inj_mem [512];
    logic [8:0]  inj_wp;
    logic [10:0] inj_len, inj_i;
    logic        inj_busy;
    logic [31:0] inj_q;
    always_ff @(posedge clk) begin
        if (win_wr && win_addr == 7'h41) inj_mem[inj_wp] <= win_wdata;
        inj_q <= inj_mem[inj_i[10:2]];
    end
    // one byte every other clock at most (the MAC takes one byte per four clocks at 100 Mb/s): the word read has a
    // clock to settle after each byte
    logic inj_rdy;
    always_ff @(posedge clk) begin
        if (rst) begin inj_wp <= '0; inj_len <= '0; inj_i <= '0; inj_busy <= 1'b0; inj_rdy <= 1'b0; end
        else begin
            inj_rdy <= inj_busy && !(j_v && j_r);
            if (win_wr && win_addr == 7'h41) inj_wp <= inj_wp + 9'd1;
            if (win_wr && win_addr == 7'h42) inj_wp <= win_wdata[8:0];
            if (win_wr && win_addr == 7'h40 && win_wdata[31] && !inj_busy && win_wdata[10:0] != '0) begin
                inj_busy <= 1'b1; inj_len <= win_wdata[10:0]; inj_i <= '0; inj_rdy <= 1'b0;
            end
            if (j_v && j_r) begin
                inj_i <= inj_i + 11'd1;
                if (j_l) inj_busy <= 1'b0;
            end
        end
    end
    assign j_v = inj_busy && inj_rdy;
    assign j_d = inj_q[8 * (3 - int'(inj_i[1:0])) +: 8];
    assign j_l = (inj_i == inj_len - 11'd1);

    // ------------------------------------------------------------------ transmit arbiter: whole frames, in turn
    logic [2:0] cur, nxt;
    logic       locked_f;
    logic [4:0] req;
    assign req = {j_v, u_v, g_v, i_v, a_v};
    always_comb begin
        nxt = cur;
        for (int k = 1; k <= 5; k++) begin
            if (req[(int'(cur) + 6 - k) % 5]) nxt = 3'((int'(cur) + 6 - k) % 5);
        end
    end
    always_ff @(posedge clk) begin
        if (rst) begin cur <= '0; locked_f <= 1'b0; end
        else if (!locked_f) begin
            if (|req) begin cur <= nxt; locked_f <= 1'b1; end
        end else if (tx_v && tx_r && tx_l) locked_f <= 1'b0;
    end
    always_comb begin
        tx_d = 8'h00; tx_v = 1'b0; tx_l = 1'b0;
        if (locked_f) case (cur)
            3'd0: begin tx_d = a_d; tx_v = a_v; tx_l = a_l; end
            3'd1: begin tx_d = i_d; tx_v = i_v; tx_l = i_l; end
            3'd2: begin tx_d = g_d; tx_v = g_v; tx_l = g_l; end
            3'd3: begin tx_d = u_d; tx_v = u_v; tx_l = u_l; end
            default: begin tx_d = j_d; tx_v = j_v; tx_l = j_l; end
        endcase
    end
    assign a_r = locked_f && cur == 3'd0 && tx_r;
    assign i_r = locked_f && cur == 3'd1 && tx_r;
    assign g_r = locked_f && cur == 3'd2 && tx_r;
    assign u_r = locked_f && cur == 3'd3 && tx_r;
    assign j_r = locked_f && cur == 3'd4 && tx_r;

    // ------------------------------------------------------------------ the frame capture (one byte per read)
    logic [7:0]  cap_mem [2048];
    logic        cap_armed, cap_done, cap_on, cap_user, first_w, cap_we;
    logic [3:0]  cap_skip;
    logic [10:0] cap_n, cap_len, cap_ra, cap_wa;
    logic [7:0]  cap_q;
    assign first_w = cap_armed && rx_sof && !cap_on && cap_skip == '0;   // the frame to capture starts now
    assign cap_we  = rx_v && (cap_on || first_w);
    assign cap_wa  = cap_on ? cap_n : 11'd0;
    always_ff @(posedge clk) begin
        if (cap_we) cap_mem[cap_wa] <= rx_d;
        cap_q <= cap_mem[cap_ra];
    end
    always_ff @(posedge clk) begin
        if (rst) begin cap_armed <= 1'b0; cap_done <= 1'b0; cap_on <= 1'b0; cap_user <= 1'b0; cap_skip <= '0;
                       cap_n <= '0; cap_len <= '0; cap_ra <= '0; end
        else begin
            if (win_wr && win_addr == 7'h49) cap_ra <= win_wdata[10:0];
            if (win_rd && win_addr == 7'h4A) cap_ra <= cap_ra + 11'd1;
            if (cap_armed && rx_sof && !cap_on && cap_skip != '0) cap_skip <= cap_skip - 4'd1;
            if (first_w) begin cap_on <= 1'b1; cap_n <= 11'd1; end
            else if (cap_on && rx_v && cap_n != 11'h7FF) cap_n <= cap_n + 11'd1;
            if ((cap_on || first_w) && rx_v && rx_l) begin
                cap_on <= 1'b0; cap_armed <= 1'b0; cap_done <= 1'b1; cap_len <= cap_on ? cap_n + 11'd1 : 11'd1;
                cap_user <= rx_u;
            end
            if (win_wr && win_addr == 7'h48 && win_wdata[0]) begin
                cap_armed <= 1'b1; cap_done <= 1'b0; cap_on <= 1'b0; cap_skip <= win_wdata[7:4];
            end
        end
    end

    // ------------------------------------------------------------------ event counters, XADC, LEDs
    logic [15:0] n_arq, n_arp, n_ping, n_pong, n_uok, n_ubad, n_q, n_rep, n_conf;
    always_ff @(posedge clk) begin
        if (rst || stat_clear) begin n_arq <= '0; n_arp <= '0; n_ping <= '0; n_pong <= '0; n_uok <= '0; n_ubad <= '0;
                                     n_q <= '0; n_rep <= '0; n_conf <= '0; end
        else begin
            n_arq <= n_arq + 16'(e_arp_req); n_arp <= n_arp + 16'(e_arp_tx_rep);
            n_ping <= n_ping + 16'(e_ping); n_pong <= n_pong + 16'(e_pong);
            n_uok <= n_uok + 16'(e_u_ok); n_ubad <= n_ubad + 16'(e_u_bad);
            n_q <= n_q + 16'(e_query); n_rep <= n_rep + 16'(e_report) + 16'(e_leave);
            n_conf <= n_conf + 16'(e_arp_conflict);
        end
    end
    logic [15:0] do_x;
    logic [7:0]  x_alm;
    logic        x_ot;
    logic        drdy, den = 1'b0;
    logic [6:0]  daddr = 7'h00;
    logic [11:0] xcode [0:3];
    logic [1:0]  xsel = '0;
    logic [19:0] xpc = '0;
    initial begin xcode[0] = '0; xcode[1] = '0; xcode[2] = '0; xcode[3] = '0; end
    /* verilator lint_off PINCONNECTEMPTY */
    XADC #(
        .INIT_40(16'h1000), .INIT_41(16'h2EF0), .INIT_42(16'h0400), .INIT_48(16'h4700), .INIT_49(16'h0000),
        .INIT_4A(16'h4700), .INIT_4B(16'h0000), .INIT_4C(16'h0000), .INIT_4D(16'h0000), .INIT_4E(16'h0000),
        .INIT_4F(16'h0000), .INIT_50(16'hB5ED), .INIT_51(16'h57E4), .INIT_52(16'hA147), .INIT_53(16'hCA33),
        .INIT_54(16'hA93A), .INIT_55(16'h52C6), .INIT_56(16'h9555), .INIT_57(16'hAE4E), .INIT_58(16'h5999),
        .INIT_5C(16'h5111), .SIM_DEVICE("7SERIES")
    ) u_xadc (
        .DCLK(clk), .DEN(den), .DWE(1'b0), .DADDR(daddr), .DI(16'h0000), .DO(do_x), .DRDY(drdy),
        .RESET(1'b0), .CONVST(1'b0), .CONVSTCLK(1'b0), .VP(1'b0), .VN(1'b0), .VAUXP(16'h0000), .VAUXN(16'h0000),
        .ALM(x_alm), .OT(x_ot), .BUSY(), .CHANNEL(), .EOC(), .EOS(), .JTAGBUSY(), .JTAGLOCKED(), .JTAGMODIFIED(), .MUXADDR());
    /* verilator lint_on PINCONNECTEMPTY */
    always_ff @(posedge clk) begin
        den <= 1'b0;
        xpc <= xpc + 1'b1;
        if (xpc == '0) begin
            daddr <= (xsel == 2'd0) ? 7'h00 : (xsel == 2'd1) ? 7'h01 : (xsel == 2'd2) ? 7'h02 : 7'h06;
            den   <= 1'b1;
        end
        if (drdy) begin xcode[xsel] <= do_x[15:4]; xsel <= xsel + 1'b1; end
    end
    // alarms latched between the host's polls (thresholds INIT_50-5C: Tj 85 C, VCCINT 0.97-1.03 V, VCCAUX 1.75-1.89 V,
    // VCCBRAM 0.95-1.05 V, over-temperature 125 C); any write to 0x3C clears them
    logic [4:0] alm_l;
    (* ASYNC_REG = "TRUE" *) logic [4:0] alm_s1, alm_s2;
    always_ff @(posedge clk) begin
        alm_s1 <= {x_ot, x_alm[3:0]};
        alm_s2 <= alm_s1;
        if (rst || (win_wr && win_addr == 7'h3C)) alm_l <= '0;
        else alm_l <= alm_l | alm_s2;
    end
    logic [25:0] beat = '0;
    logic [21:0] rx_led = '0, tx_led = '0;
    always_ff @(posedge clk) begin
        beat <= beat + 1'b1;
        rx_led <= (rx_v && rx_l) ? '1 : (rx_led != '0 ? rx_led - 1'b1 : rx_led);
        tx_led <= (tx_v && tx_r && tx_l) ? '1 : (tx_led != '0 ? tx_led - 1'b1 : tx_led);
    end
    assign LED = {n_pong != 16'd0, tx_led != '0, rx_led != '0, beat[25]};

    // ------------------------------------------------------------------ window read mux (valid the clock after win_rd)
    always_ff @(posedge clk) begin
        casez (win_addr)
            7'h00: win_rdata <= {27'b0, speed_100, phy_rst, mcast_all, bcast_en, promisc};
            7'h01: win_rdata <= {16'b0, own_mac[47:32]};
            7'h02: win_rdata <= own_mac[31:0];
            7'h03: win_rdata <= own_ip;
            7'h04: win_rdata <= {md_busy, 15'b0, md_rdata};
            7'h05: win_rdata <= grp0;
            7'h06: win_rdata <= grp1;
            7'h07: win_rdata <= {30'b0, group_en};
            7'h08: win_rdata <= {16'b0, udp_port};
            7'h1?, 7'h2?: win_rdata <= (win_addr <= 7'h24) ? st_data : 32'd0;
            7'h30: win_rdata <= {n_arq, n_arp};
            7'h31: win_rdata <= {n_ping, n_pong};
            7'h32: win_rdata <= {n_uok, n_ubad};
            7'h33: win_rdata <= {n_q, n_rep};
            7'h34: win_rdata <= {n_svc, n_miss};
            7'h35: win_rdata <= {16'b0, n_conf};
            7'h38: win_rdata <= {20'b0, xcode[0]};
            7'h39: win_rdata <= {20'b0, xcode[1]};
            7'h3A: win_rdata <= {20'b0, xcode[2]};
            7'h3B: win_rdata <= {20'b0, xcode[3]};
            7'h3C: win_rdata <= {27'b0, alm_l};
            7'h40: win_rdata <= {inj_busy, 20'b0, inj_len};
            7'h48: win_rdata <= {cap_done, cap_user, 19'b0, cap_len};
            7'h4A: win_rdata <= {24'b0, cap_q};
            default: win_rdata <= '0;
        endcase
    end
endmodule
/* verilator lint_on UNUSEDSIGNAL */
