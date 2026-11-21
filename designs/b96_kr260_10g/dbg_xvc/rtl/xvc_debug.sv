// xvc_debug.sv (brief 131, build dbg_xvc only): lets Vivado's hardware manager reach an ILA over the network, with no JTAG traffic while the board's Linux runs.
//   PS M_AXI_HPM0_LPD (AXI4, 100 MHz pl_clk0) -> axi_protocol_converter (AXI4 to AXI4-Lite) -> Debug Bridge ("From AXI to BSCAN") -> the ILA's debug hub (inserted by Vivado)
// Software on the board's Linux (an XVC server, docs/xvc_board_side.md) turns Vivado's XVC (Xilinx Virtual Cable) TCP commands into reads and writes of the bridge's
// five registers; the bridge drives a soft JTAG TAP that the ILA's debug hub sits on. The ILA samples the clk-domain taps of b96_core (docs/dbg_xvc.md lists each bit and why).
// Nothing in this module drives the design: the taps are inputs only. The three RXUSRCLK2-domain strobes cross to clk by xpm_cdc_pulse (a pulse per strobe; a second strobe
// inside the crossing's dead time of a few clocks is dropped, which is stated in docs/dbg_xvc.md).
module xvc_debug (
    input  logic        clk,            // the design's 100 MHz free-running clock (MMCM output): the ILA's sample clock
    input  logic [34:0] dbg_s,          // clk-domain taps, bit meaning in docs/dbg_xvc.md
    input  logic        dbg_rxclk,      // RXUSRCLK2
    input  logic [2:0]  dbg_rxp         // RXUSRCLK2-domain strobes
);
    // ---- the PS and its AXI master (default configuration: M_AXI_HPM0_LPD enabled, pl_clk0 = 100 MHz; nothing else of the PS is used) ----
    logic        pl_clk0, pl_resetn0, aresetn_pl, rst_pl;
    logic [15:0] awid, arid, bid, rid;
    logic [39:0] awaddr, araddr;
    logic [7:0]  awlen, arlen;
    logic [2:0]  awsize, arsize, awprot, arprot;
    logic [1:0]  awburst, arburst, bresp, rresp;
    logic        awlock, arlock, awvalid, arvalid, awready, arready, wlast, wvalid, wready, bvalid, bready, rlast, rvalid, rready;
    logic [3:0]  awcache, arcache, awqos, arqos;
    logic [31:0] wdata, rdata;
    logic [3:0]  wstrb;
    logic [15:0] awuser, aruser;
    psu_xvc u_ps (
        .maxihpm0_lpd_aclk(pl_clk0),
        .maxigp2_awid(awid), .maxigp2_awaddr(awaddr), .maxigp2_awlen(awlen), .maxigp2_awsize(awsize), .maxigp2_awburst(awburst),
        .maxigp2_awlock(awlock), .maxigp2_awcache(awcache), .maxigp2_awprot(awprot), .maxigp2_awvalid(awvalid), .maxigp2_awuser(awuser),
        .maxigp2_awready(awready), .maxigp2_wdata(wdata), .maxigp2_wstrb(wstrb), .maxigp2_wlast(wlast), .maxigp2_wvalid(wvalid),
        .maxigp2_wready(wready), .maxigp2_bid(bid), .maxigp2_bresp(bresp), .maxigp2_bvalid(bvalid), .maxigp2_bready(bready),
        .maxigp2_arid(arid), .maxigp2_araddr(araddr), .maxigp2_arlen(arlen), .maxigp2_arsize(arsize), .maxigp2_arburst(arburst),
        .maxigp2_arlock(arlock), .maxigp2_arcache(arcache), .maxigp2_arprot(arprot), .maxigp2_arvalid(arvalid), .maxigp2_aruser(aruser),
        .maxigp2_arready(arready), .maxigp2_rid(rid), .maxigp2_rdata(rdata), .maxigp2_rresp(rresp), .maxigp2_rlast(rlast),
        .maxigp2_rvalid(rvalid), .maxigp2_rready(rready), .maxigp2_awqos(awqos), .maxigp2_arqos(arqos),
        .pl_resetn0(pl_resetn0), .pl_clk0(pl_clk0));
    // the PS reset is asynchronous to pl_clk0: synchronise it (the only asynchronous reset use here, a synchroniser)
    xpm_cdc_sync_rst #(.DEST_SYNC_FF(4), .INIT(1), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1)) u_rst (.src_rst(!pl_resetn0), .dest_clk(pl_clk0), .dest_rst(rst_pl));
    assign aresetn_pl = !rst_pl;

    // ---- AXI4 to AXI4-Lite, then the Debug Bridge's five registers ----
    logic [31:0] l_awaddr, l_araddr, l_wdata, l_rdata;
    logic [2:0]  l_awprot, l_arprot;
    logic [3:0]  l_wstrb;
    logic [1:0]  l_bresp, l_rresp;
    logic        l_awvalid, l_awready, l_wvalid, l_wready, l_bvalid, l_bready, l_arvalid, l_arready, l_rvalid, l_rready;
    apc_xvc u_apc (
        .aclk(pl_clk0), .aresetn(aresetn_pl),
        .s_axi_awid(awid), .s_axi_awaddr(awaddr[31:0]), .s_axi_awlen(awlen), .s_axi_awsize(awsize), .s_axi_awburst(awburst), .s_axi_awlock(awlock),
        .s_axi_awcache(awcache), .s_axi_awprot(awprot), .s_axi_awregion(4'd0), .s_axi_awqos(awqos), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wlast(wlast), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bid(bid), .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_arid(arid), .s_axi_araddr(araddr[31:0]), .s_axi_arlen(arlen), .s_axi_arsize(arsize), .s_axi_arburst(arburst), .s_axi_arlock(arlock),
        .s_axi_arcache(arcache), .s_axi_arprot(arprot), .s_axi_arregion(4'd0), .s_axi_arqos(arqos), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rid(rid), .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rlast(rlast), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .m_axi_awaddr(l_awaddr), .m_axi_awprot(l_awprot), .m_axi_awvalid(l_awvalid), .m_axi_awready(l_awready),
        .m_axi_wdata(l_wdata), .m_axi_wstrb(l_wstrb), .m_axi_wvalid(l_wvalid), .m_axi_wready(l_wready),
        .m_axi_bresp(l_bresp), .m_axi_bvalid(l_bvalid), .m_axi_bready(l_bready),
        .m_axi_araddr(l_araddr), .m_axi_arprot(l_arprot), .m_axi_arvalid(l_arvalid), .m_axi_arready(l_arready),
        .m_axi_rdata(l_rdata), .m_axi_rresp(l_rresp), .m_axi_rvalid(l_rvalid), .m_axi_rready(l_rready));
    dbb_xvc u_bridge (
        .s_axi_aclk(pl_clk0), .s_axi_aresetn(aresetn_pl),
        .S_AXI_araddr(l_araddr[4:0]), .S_AXI_arprot(l_arprot), .S_AXI_arready(l_arready), .S_AXI_arvalid(l_arvalid),
        .S_AXI_awaddr(l_awaddr[4:0]), .S_AXI_awprot(l_awprot), .S_AXI_awready(l_awready), .S_AXI_awvalid(l_awvalid),
        .S_AXI_bready(l_bready), .S_AXI_bresp(l_bresp), .S_AXI_bvalid(l_bvalid),
        .S_AXI_rdata(l_rdata), .S_AXI_rready(l_rready), .S_AXI_rresp(l_rresp), .S_AXI_rvalid(l_rvalid),
        .S_AXI_wdata(l_wdata), .S_AXI_wready(l_wready), .S_AXI_wstrb(l_wstrb), .S_AXI_wvalid(l_wvalid));

    // ---- the strobes of RXUSRCLK2 into clk, then the ILA ----
    logic [2:0] rxp_c;
    for (genvar i = 0; i < 3; i++) begin : g_p
        xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(1)) u_x (
            .src_clk(dbg_rxclk), .src_pulse(dbg_rxp[i]), .src_rst(1'b0), .dest_clk(clk), .dest_pulse(rxp_c[i]), .dest_rst(1'b0));
    end
    ila_xvc u_ila (.clk, .probe0({rxp_c, dbg_s}));
endmodule
