// kr260_top.sv: the mock trading path on the Kria KR260 carrier's two PL Gigabit Ethernet ports.
//
// Port A (J10B, Ethernet 2, PHY2 on HPA) is the trading port; port B (J10A, Ethernet 3, PHY3 on HPB) is the bench
// source, so a cable between J10A and J10B closes the loop with both ends timed by one counter. Both PHYs are Marvell
// M88E1111 in RGMII mode (the project knowledge base, board/kr260/ethernet; pins from the AMD kr260 board files).
// Clocks: the 25 MHz HPA input (25 MHz is the figure an open-source KR260 reference design uses; unconfirmed against the schematic) -> MMCM ->
// 125 MHz core clock and a 90-degree copy for TXC. Each port's RX_CLK is its own clock domain (gmii_cdc).
// The PS is not used: the host reaches the registers over the JTAG cable (jtag_bus). The PHYs are held in reset for
// 2^21 clocks (16.8 ms) after the MMCM locks; the M88E1111 needs at least 10 ms.

module kr260_top #(
    parameter logic [31:0] BUILD_STAMP = 32'h0,
    parameter int          RX_IDELAY_PS = 1000      // receive data delay (IDELAYE3, TIME mode), from the timing analysis
) (
    input  logic       clk_25,
    // port A: PHY2, J10B
    input  logic       a_rxc,
    input  logic [3:0] a_rxd,
    input  logic       a_rx_ctl,
    output logic       a_txc,
    output logic [3:0] a_txd,
    output logic       a_tx_ctl,
    output logic       a_rst_n,
    output logic       a_mdc,
    inout  wire        a_mdio,
    // port B: PHY3, J10A
    input  logic       b_rxc,
    input  logic [3:0] b_rxd,
    input  logic       b_rx_ctl,
    output logic       b_txc,
    output logic [3:0] b_txd,
    output logic       b_tx_ctl,
    output logic       b_rst_n,
    output logic       b_mdc,
    inout  wire        b_mdio,
    output logic [1:0] led
);
    // ---- clocks and resets ----
    logic clk, clk90, locked, fb, clk0_u, clk90_u, rst, rst_a, rst_b;
`ifdef SYNTHESIS
    MMCME4_BASE #(.CLKIN1_PERIOD(40.0), .CLKFBOUT_MULT_F(40.0), .DIVCLK_DIVIDE(1),
                  .CLKOUT0_DIVIDE_F(8.0), .CLKOUT1_DIVIDE(8), .CLKOUT1_PHASE(90.0), .CLKOUT2_DIVIDE(3)) u_mmcm (
        .CLKIN1(clk_25), .CLKFBIN(fb), .CLKFBOUT(fb), .CLKFBOUTB(), .CLKOUT0(clk0_u), .CLKOUT0B(), .CLKOUT1(clk90_u),
        .CLKOUT1B(), .CLKOUT2(ref333_u), .CLKOUT2B(), .CLKOUT3(), .CLKOUT3B(), .CLKOUT4(), .CLKOUT5(), .CLKOUT6(),
        .LOCKED(locked), .PWRDWN(1'b0), .RST(1'b0));
    BUFG u_bg0 (.I(clk0_u), .O(clk));
    BUFG u_bg1 (.I(clk90_u), .O(clk90));
    // Receive clocks: each RX_CLK through a global buffer (the KR260's RX_CLK pins cannot reach an MMCM on a
    // dedicated route). The buffer delays the capture edge by about 2 ns, so the data are delayed to match: rgmii_rx's
    // IDELAYE3 (RX_IDELAY_PS, calibrated by the IDELAYCTRL below) moves the PHY's centre-aligned data window onto the
    // capture edge.
    logic a_rxc_g, b_rxc_g;
    BUFG u_bga (.I(a_rxc), .O(a_rxc_g));
    BUFG u_bgb (.I(b_rxc), .O(b_rxc_g));
    // IDELAYCTRL: 333.33 MHz reference from the core MMCM (VCO 1000 MHz / 3), held in reset until the MMCM locks; its
    // reset is asserted at once and released on a reference clock edge, from flip-flops clocked by the reference
    logic ref333_u, ref333, dly_rdy, rst_ref;
    BUFG u_bgref (.I(ref333_u), .O(ref333));
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rstref (
        .src_arst(!locked), .dest_clk(ref333), .dest_arst(rst_ref));
    (* IODELAY_GROUP = "rgmii_rx" *) IDELAYCTRL #(.SIM_DEVICE("ULTRASCALE_PLUS")) u_idc (.REFCLK(ref333), .RST(rst_ref),
        .RDY(dly_rdy));
`else
    // simulation: no MMCM; the core runs on the input clock and "lock" rises after 16 clocks, as it does on silicon
    logic [4:0] lk = 5'd0;
    always_ff @(posedge clk_25) if (!lk[4]) lk <= lk + 5'd1;
    assign clk = clk_25; assign clk90 = clk_25; assign locked = lk[4];
    logic a_rxc_g, b_rxc_g, dly_rdy;
    assign a_rxc_g = a_rxc; assign b_rxc_g = b_rxc; assign dly_rdy = 1'b1;                     // no delay lines
`endif
    xpm_cdc_sync_rst #(.DEST_SYNC_FF(4), .INIT(1), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0)) u_rst (
        .src_rst(!locked), .dest_clk(clk), .dest_rst(rst));
    // each receive path stays in reset until the delay lines are calibrated: IDELAYCTRL's RDY (asynchronous) is
    // synchronised into the core clock, combined with the core reset in a flip-flop, and that registered reset is
    // what each receive clock's reset synchroniser takes (no logic in front of a synchroniser)
    logic rdy_c, rx_rst_q;
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_rdy (
        .src_clk(1'b0), .src_in(dly_rdy), .dest_clk(clk), .dest_out(rdy_c));
    always_ff @(posedge clk) rx_rst_q <= rst || !rdy_c;
    xpm_cdc_sync_rst #(.DEST_SYNC_FF(4), .INIT(1), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0)) u_rsta (
        .src_rst(rx_rst_q), .dest_clk(a_rxc_g), .dest_rst(rst_a));
    xpm_cdc_sync_rst #(.DEST_SYNC_FF(4), .INIT(1), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0)) u_rstb (
        .src_rst(rx_rst_q), .dest_clk(b_rxc_g), .dest_rst(rst_b));

    logic [21:0] prst;
    logic        phy_force;
    always_ff @(posedge clk) prst <= rst ? 22'd0 : (prst[21] ? prst : prst + 22'd1);
    assign a_rst_n = prst[21] && !phy_force;
    assign b_rst_n = prst[21] && !phy_force;

    // ---- RGMII ----
    logic [7:0] ag_d, bg_d, a_txd8, b_txd8;
    logic       ag_dv, ag_er, bg_dv, bg_er, a_txen, b_txen;
    // ip_lib/eth_mac_rgmii blocks, at 1000 Mb/s only on this bench
    logic ag_v, bg_v;
    rgmii_rx #(.IDELAY_PS(RX_IDELAY_PS)) u_arx (.rx_clk(a_rxc_g), .speed(2'd2), .rxd(a_rxd), .rx_ctl(a_rx_ctl), .gmii_d(ag_d), .gmii_v(ag_v),
                    .gmii_dv(ag_dv), .gmii_er(ag_er));
    rgmii_rx #(.IDELAY_PS(RX_IDELAY_PS)) u_brx (.rx_clk(b_rxc_g), .speed(2'd2), .rxd(b_rxd), .rx_ctl(b_rx_ctl), .gmii_d(bg_d), .gmii_v(bg_v),
                    .gmii_dv(bg_dv), .gmii_er(bg_er));
    rgmii_tx #(.TXC_CLK90(0)) u_atx (.clk, .clk90, .rst, .speed(2'd2), .ce(), .gmii_d(a_txd8), .gmii_en(a_txen), .gmii_er(1'b0), .txd(a_txd), .tx_ctl(a_tx_ctl),
                    .txc(a_txc));
    rgmii_tx #(.TXC_CLK90(0)) u_btx (.clk, .clk90, .rst, .speed(2'd2), .ce(), .gmii_d(b_txd8), .gmii_en(b_txen), .gmii_er(1'b0), .txd(b_txd), .tx_ctl(b_tx_ctl),
                    .txc(b_txc));

    logic       a_v, a_eof, a_er, a_ovf, b_v, b_eof, b_er, b_ovf;
    logic [7:0] a_d, b_d;
    logic [31:0] a_cnt, b_cnt;
    gmii_cdc u_acdc (.rx_clk(a_rxc_g), .rx_rst(rst_a), .gmii_d(ag_d), .gmii_v(ag_v), .gmii_dv(ag_dv), .gmii_er(ag_er), .clk,
                     .o_v(a_v), .o_eof(a_eof), .o_er(a_er), .o_d(a_d), .o_ovf(a_ovf), .o_rxclk_cnt(a_cnt));
    gmii_cdc u_bcdc (.rx_clk(b_rxc_g), .rx_rst(rst_b), .gmii_d(bg_d), .gmii_v(bg_v), .gmii_dv(bg_dv), .gmii_er(bg_er), .clk,
                     .o_v(b_v), .o_eof(b_eof), .o_er(b_er), .o_d(b_d), .o_ovf(b_ovf), .o_rxclk_cnt(b_cnt));

    // ---- MDIO pins ----
    logic a_mdo, a_mdt, a_mdi, b_mdo, b_mdt, b_mdi;
    assign a_mdio = a_mdt ? 1'bz : a_mdo;
    assign b_mdio = b_mdt ? 1'bz : b_mdo;
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_amdi (
        .src_clk(1'b0), .src_in(a_mdio), .dest_clk(clk), .dest_out(a_mdi));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_bmdi (
        .src_clk(1'b0), .src_in(b_mdio), .dest_clk(clk), .dest_out(b_mdi));

    // ---- operating conditions: SYSMONE4 on the core clock's DRP ----
    logic        drp_en, drp_we, drp_rdy;
    logic [7:0]  drp_addr;
    logic [15:0] drp_di, drp_do;
    logic [7:0]  alarms;
`ifdef SYNTHESIS
    logic [15:0] alm;
    logic        ot;
    SYSMONE4 #(.SIM_MONITOR_FILE("none"), .SIM_DEVICE("ZYNQ_ULTRASCALE")) u_sysmon (
        .DCLK(clk), .DEN(drp_en), .DWE(drp_we), .DADDR(drp_addr), .DI(drp_di), .DO(drp_do), .DRDY(drp_rdy),
        .RESET(rst), .CONVST(1'b0), .CONVSTCLK(1'b0), .VP(1'b0), .VN(1'b0), .VAUXP(16'h0), .VAUXN(16'h0),
        .ALM(alm), .OT(ot), .BUSY(), .CHANNEL(), .EOC(), .EOS(), .JTAGBUSY(), .JTAGLOCKED(), .JTAGMODIFIED(),
        .MUXADDR(), .ADC_DATA(), .I2C_SCLK(1'b1), .I2C_SDA(1'b1), .I2C_SCLK_TS(), .I2C_SDA_TS(), .SMBALERT_TS());
    assign alarms = {ot, alm[6:0]};
`else
    assign drp_do = 16'h0; assign drp_rdy = drp_en; assign alarms = '0;
`endif

    // ---- host bus ----
    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata;
    jtag_bus u_jtag (.clk, .rst, .h_we, .h_re, .h_addr, .h_wdata, .h_rdata);

    trigger_core #(.BUILD_STAMP(BUILD_STAMP)) u_core (.clk, .rst,
        .a_rx_v(a_v), .a_rx_eof(a_eof), .a_rx_er(a_er), .a_rx_d(a_d), .a_rx_ovf(a_ovf), .a_txd(a_txd8), .a_tx_en(a_txen),
        .b_rx_v(b_v), .b_rx_eof(b_eof), .b_rx_er(b_er), .b_rx_d(b_d), .b_rx_ovf(b_ovf), .b_txd(b_txd8), .b_tx_en(b_txen),
        .a_mdc, .a_mdio_o(a_mdo), .a_mdio_t(a_mdt), .a_mdio_i(a_mdi),
        .b_mdc, .b_mdio_o(b_mdo), .b_mdio_t(b_mdt), .b_mdio_i(b_mdi),
        .phy_rst_force(phy_force), .a_rxclk_cnt(a_cnt), .b_rxclk_cnt(b_cnt),
        .drp_en, .drp_we, .drp_addr, .drp_di, .drp_do, .drp_rdy, .alarms,
        .kill_in(1'b0), .pins(led),
        .h_we, .h_re, .h_addr, .h_wdata, .h_rdata);
endmodule
