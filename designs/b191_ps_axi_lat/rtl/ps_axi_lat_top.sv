// ps_axi_lat_top.sv: the PL image of board row B-R8 (brief 191): the Zynq UltraScale+ PS's two AXI masters towards the programmable logic, each with an axi_lat_probe.
//   M_AXI_HPM0_FPD (full-power domain, the master used for fast control registers) -> probe at the PS address window 0xA0000000
//   M_AXI_HPM0_LPD (low-power domain, the one the debug bridge of dbg_xvc uses)    -> probe at the PS address window 0x80000000
// Both masters run on pl_clk0 (100 MHz, a fabric clock of 10 ns) and are 32 bits wide, so a 32-bit access is a single beat. There are no I/O pins: the PS's own pins are dedicated and the
// design has no other connection. A latency measurement image only (never part of a design whose latency matters otherwise).
module ps_axi_lat_top #(
    parameter logic [31:0] BUILD_STAMP = 32'hB191_0F01        // the flow overrides it with the sources' stamp; both probes return it in BUILD
) (
    output logic unused_o                // a placeholder output so that the design has a port; it is tied low
);
    assign unused_o = 1'b0;
    logic        pl_clk0, pl_resetn0, rst_pl, aresetn;
    // FPD master (maxigp0_*) and LPD master (maxigp2_*)
    logic [15:0] f_awid, f_arid, f_bid, f_rid, l_awid, l_arid, l_bid, l_rid;
    logic [39:0] f_awaddr, f_araddr, l_awaddr, l_araddr;
    logic [7:0]  f_awlen, f_arlen, l_awlen, l_arlen;
    logic [2:0]  f_awsize, f_arsize, f_awprot, f_arprot, l_awsize, l_arsize, l_awprot, l_arprot;
    logic [1:0]  f_awburst, f_arburst, f_bresp, f_rresp, l_awburst, l_arburst, l_bresp, l_rresp;
    logic        f_awlock, f_arlock, f_awvalid, f_arvalid, f_awready, f_arready, f_wlast, f_wvalid, f_wready, f_bvalid, f_bready, f_rlast, f_rvalid, f_rready;
    logic        l_awlock, l_arlock, l_awvalid, l_arvalid, l_awready, l_arready, l_wlast, l_wvalid, l_wready, l_bvalid, l_bready, l_rlast, l_rvalid, l_rready;
    logic [3:0]  f_awcache, f_arcache, f_awqos, f_arqos, l_awcache, l_arcache, l_awqos, l_arqos;
    logic [31:0] f_wdata, f_rdata, l_wdata, l_rdata;
    logic [3:0]  f_wstrb, l_wstrb;
    logic [15:0] f_awuser, f_aruser, l_awuser, l_aruser;
    psu_lat u_ps (
        .maxihpm0_fpd_aclk(pl_clk0), .maxihpm0_lpd_aclk(pl_clk0),
        .maxigp0_awid(f_awid), .maxigp0_awaddr(f_awaddr), .maxigp0_awlen(f_awlen), .maxigp0_awsize(f_awsize), .maxigp0_awburst(f_awburst),
        .maxigp0_awlock(f_awlock), .maxigp0_awcache(f_awcache), .maxigp0_awprot(f_awprot), .maxigp0_awvalid(f_awvalid), .maxigp0_awuser(f_awuser),
        .maxigp0_awready(f_awready), .maxigp0_wdata(f_wdata), .maxigp0_wstrb(f_wstrb), .maxigp0_wlast(f_wlast), .maxigp0_wvalid(f_wvalid),
        .maxigp0_wready(f_wready), .maxigp0_bid(f_bid), .maxigp0_bresp(f_bresp), .maxigp0_bvalid(f_bvalid), .maxigp0_bready(f_bready),
        .maxigp0_arid(f_arid), .maxigp0_araddr(f_araddr), .maxigp0_arlen(f_arlen), .maxigp0_arsize(f_arsize), .maxigp0_arburst(f_arburst),
        .maxigp0_arlock(f_arlock), .maxigp0_arcache(f_arcache), .maxigp0_arprot(f_arprot), .maxigp0_arvalid(f_arvalid), .maxigp0_aruser(f_aruser),
        .maxigp0_arready(f_arready), .maxigp0_rid(f_rid), .maxigp0_rdata(f_rdata), .maxigp0_rresp(f_rresp), .maxigp0_rlast(f_rlast),
        .maxigp0_rvalid(f_rvalid), .maxigp0_rready(f_rready), .maxigp0_awqos(f_awqos), .maxigp0_arqos(f_arqos),
        .maxigp2_awid(l_awid), .maxigp2_awaddr(l_awaddr), .maxigp2_awlen(l_awlen), .maxigp2_awsize(l_awsize), .maxigp2_awburst(l_awburst),
        .maxigp2_awlock(l_awlock), .maxigp2_awcache(l_awcache), .maxigp2_awprot(l_awprot), .maxigp2_awvalid(l_awvalid), .maxigp2_awuser(l_awuser),
        .maxigp2_awready(l_awready), .maxigp2_wdata(l_wdata), .maxigp2_wstrb(l_wstrb), .maxigp2_wlast(l_wlast), .maxigp2_wvalid(l_wvalid),
        .maxigp2_wready(l_wready), .maxigp2_bid(l_bid), .maxigp2_bresp(l_bresp), .maxigp2_bvalid(l_bvalid), .maxigp2_bready(l_bready),
        .maxigp2_arid(l_arid), .maxigp2_araddr(l_araddr), .maxigp2_arlen(l_arlen), .maxigp2_arsize(l_arsize), .maxigp2_arburst(l_arburst),
        .maxigp2_arlock(l_arlock), .maxigp2_arcache(l_arcache), .maxigp2_arprot(l_arprot), .maxigp2_arvalid(l_arvalid), .maxigp2_aruser(l_aruser),
        .maxigp2_arready(l_arready), .maxigp2_rid(l_rid), .maxigp2_rdata(l_rdata), .maxigp2_rresp(l_rresp), .maxigp2_rlast(l_rlast),
        .maxigp2_rvalid(l_rvalid), .maxigp2_rready(l_rready), .maxigp2_awqos(l_awqos), .maxigp2_arqos(l_arqos),
        .pl_resetn0(pl_resetn0), .pl_clk0(pl_clk0));
    // the PS reset is asynchronous to pl_clk0: synchronise it (the only asynchronous reset use here, a synchroniser)
    xpm_cdc_sync_rst #(.DEST_SYNC_FF(4), .INIT(1), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1)) u_rst (.src_rst(!pl_resetn0), .dest_clk(pl_clk0), .dest_rst(rst_pl));
    assign aresetn = !rst_pl;

    axi_lat_probe #(.BUILD_ID(BUILD_STAMP), .CLK_HZ(32'd100_000_000)) u_fpd (
        .aclk(pl_clk0), .aresetn,
        .awid(f_awid), .awaddr(f_awaddr[31:0]), .awlen(f_awlen), .awsize(f_awsize), .awvalid(f_awvalid), .awready(f_awready),
        .wdata(f_wdata), .wstrb(f_wstrb), .wlast(f_wlast), .wvalid(f_wvalid), .wready(f_wready),
        .bid(f_bid), .bresp(f_bresp), .bvalid(f_bvalid), .bready(f_bready),
        .arid(f_arid), .araddr(f_araddr[31:0]), .arlen(f_arlen), .arsize(f_arsize), .arvalid(f_arvalid), .arready(f_arready),
        .rid(f_rid), .rdata(f_rdata), .rresp(f_rresp), .rlast(f_rlast), .rvalid(f_rvalid), .rready(f_rready));
    axi_lat_probe #(.BUILD_ID(BUILD_STAMP), .CLK_HZ(32'd100_000_000)) u_lpd (
        .aclk(pl_clk0), .aresetn,
        .awid(l_awid), .awaddr(l_awaddr[31:0]), .awlen(l_awlen), .awsize(l_awsize), .awvalid(l_awvalid), .awready(l_awready),
        .wdata(l_wdata), .wstrb(l_wstrb), .wlast(l_wlast), .wvalid(l_wvalid), .wready(l_wready),
        .bid(l_bid), .bresp(l_bresp), .bvalid(l_bvalid), .bready(l_bready),
        .arid(l_arid), .araddr(l_araddr[31:0]), .arlen(l_arlen), .arsize(l_arsize), .arvalid(l_arvalid), .arready(l_arready),
        .rid(l_rid), .rdata(l_rdata), .rresp(l_rresp), .rlast(l_rlast), .rvalid(l_rvalid), .rready(l_rready));
    logic unused;
    assign unused = &{1'b0, f_awburst, f_awlock, f_awcache, f_awprot, f_awqos, f_awuser, f_arburst, f_arlock, f_arcache, f_arprot, f_arqos, f_aruser, f_awaddr[39:32], f_araddr[39:32],
                      l_awburst, l_awlock, l_awcache, l_awprot, l_awqos, l_awuser, l_arburst, l_arlock, l_arcache, l_arprot, l_arqos, l_aruser, l_awaddr[39:32], l_araddr[39:32]};
endmodule
