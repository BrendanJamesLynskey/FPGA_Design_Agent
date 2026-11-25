// axi4_reg_slice.sv: an AXI4 (full) register slice for all five channels, one pipe_reg_core chain per channel (brief 151).
// Carried: id, addr, len, size, burst, lock, cache, prot, qos (AW and AR); data, strb, last (W); id, resp (B); id, data, resp, last (R).
// NOT carried (so the block cannot be used where they matter): awregion/arregion and the awuser/wuser/buser/aruser/ruser signals,
// and AXI3 wid. Per-channel MODE, N slices in series; see axil_reg_slice.sv for the rest.
module axi4_reg_slice #(
    parameter int ADDR_W = 32,
    parameter int DATA_W = 32,
    parameter int ID_W   = 4,
    parameter int N      = 1,
    parameter int MODE_AW = 1,
    parameter int MODE_W = 1,
    parameter int MODE_B = 1,
    parameter int MODE_AR = 1,
    parameter int MODE_R = 1
) (
    input  logic aclk,
    input  logic aresetn,
    input  logic s_axi_awvalid,
    output logic s_axi_awready,
    input  logic [ID_W-1:0] s_axi_awid,
    input  logic [ADDR_W-1:0] s_axi_awaddr,
    input  logic [8-1:0] s_axi_awlen,
    input  logic [3-1:0] s_axi_awsize,
    input  logic [2-1:0] s_axi_awburst,
    input  logic [1-1:0] s_axi_awlock,
    input  logic [4-1:0] s_axi_awcache,
    input  logic [3-1:0] s_axi_awprot,
    input  logic [4-1:0] s_axi_awqos,
    output logic m_axi_awvalid,
    input  logic m_axi_awready,
    output logic [ID_W-1:0] m_axi_awid,
    output logic [ADDR_W-1:0] m_axi_awaddr,
    output logic [8-1:0] m_axi_awlen,
    output logic [3-1:0] m_axi_awsize,
    output logic [2-1:0] m_axi_awburst,
    output logic [1-1:0] m_axi_awlock,
    output logic [4-1:0] m_axi_awcache,
    output logic [3-1:0] m_axi_awprot,
    output logic [4-1:0] m_axi_awqos,
    input  logic s_axi_wvalid,
    output logic s_axi_wready,
    input  logic [DATA_W-1:0] s_axi_wdata,
    input  logic [DATA_W/8-1:0] s_axi_wstrb,
    input  logic [1-1:0] s_axi_wlast,
    output logic m_axi_wvalid,
    input  logic m_axi_wready,
    output logic [DATA_W-1:0] m_axi_wdata,
    output logic [DATA_W/8-1:0] m_axi_wstrb,
    output logic [1-1:0] m_axi_wlast,
    output logic s_axi_bvalid,
    input  logic s_axi_bready,
    output logic [ID_W-1:0] s_axi_bid,
    output logic [2-1:0] s_axi_bresp,
    input  logic m_axi_bvalid,
    output logic m_axi_bready,
    input  logic [ID_W-1:0] m_axi_bid,
    input  logic [2-1:0] m_axi_bresp,
    input  logic s_axi_arvalid,
    output logic s_axi_arready,
    input  logic [ID_W-1:0] s_axi_arid,
    input  logic [ADDR_W-1:0] s_axi_araddr,
    input  logic [8-1:0] s_axi_arlen,
    input  logic [3-1:0] s_axi_arsize,
    input  logic [2-1:0] s_axi_arburst,
    input  logic [1-1:0] s_axi_arlock,
    input  logic [4-1:0] s_axi_arcache,
    input  logic [3-1:0] s_axi_arprot,
    input  logic [4-1:0] s_axi_arqos,
    output logic m_axi_arvalid,
    input  logic m_axi_arready,
    output logic [ID_W-1:0] m_axi_arid,
    output logic [ADDR_W-1:0] m_axi_araddr,
    output logic [8-1:0] m_axi_arlen,
    output logic [3-1:0] m_axi_arsize,
    output logic [2-1:0] m_axi_arburst,
    output logic [1-1:0] m_axi_arlock,
    output logic [4-1:0] m_axi_arcache,
    output logic [3-1:0] m_axi_arprot,
    output logic [4-1:0] m_axi_arqos,
    output logic s_axi_rvalid,
    input  logic s_axi_rready,
    output logic [ID_W-1:0] s_axi_rid,
    output logic [DATA_W-1:0] s_axi_rdata,
    output logic [2-1:0] s_axi_rresp,
    output logic [1-1:0] s_axi_rlast,
    input  logic m_axi_rvalid,
    output logic m_axi_rready,
    input  logic [ID_W-1:0] m_axi_rid,
    input  logic [DATA_W-1:0] m_axi_rdata,
    input  logic [2-1:0] m_axi_rresp,
    input  logic [1-1:0] m_axi_rlast
);
    // AW channel: slave port to master port
    localparam int PW_AW = (ID_W) + (ADDR_W) + (8) + (3) + (2) + (1) + (4) + (3) + (4);
    wire [PW_AW-1:0] aw_in = {s_axi_awid, s_axi_awaddr, s_axi_awlen, s_axi_awsize, s_axi_awburst, s_axi_awlock, s_axi_awcache, s_axi_awprot, s_axi_awqos};
    wire [PW_AW-1:0] aw_out;
    pipe_reg_core #(.W(PW_AW), .N(N), .MODE(MODE_AW)) u_aw (.clk(aclk), .rst(!aresetn), .s_valid(s_axi_awvalid), .s_ready(s_axi_awready),
        .s_data(aw_in), .m_valid(m_axi_awvalid), .m_ready(m_axi_awready), .m_data(aw_out));
    assign m_axi_awqos = aw_out[0 +: 4];
    assign m_axi_awprot = aw_out[0 + (4) +: 3];
    assign m_axi_awcache = aw_out[0 + (4) + (3) +: 4];
    assign m_axi_awlock = aw_out[0 + (4) + (3) + (4) +: 1];
    assign m_axi_awburst = aw_out[0 + (4) + (3) + (4) + (1) +: 2];
    assign m_axi_awsize = aw_out[0 + (4) + (3) + (4) + (1) + (2) +: 3];
    assign m_axi_awlen = aw_out[0 + (4) + (3) + (4) + (1) + (2) + (3) +: 8];
    assign m_axi_awaddr = aw_out[0 + (4) + (3) + (4) + (1) + (2) + (3) + (8) +: ADDR_W];
    assign m_axi_awid = aw_out[0 + (4) + (3) + (4) + (1) + (2) + (3) + (8) + (ADDR_W) +: ID_W];
    // W channel: slave port to master port
    localparam int PW_W = (DATA_W) + (DATA_W/8) + (1);
    wire [PW_W-1:0] w_in = {s_axi_wdata, s_axi_wstrb, s_axi_wlast};
    wire [PW_W-1:0] w_out;
    pipe_reg_core #(.W(PW_W), .N(N), .MODE(MODE_W)) u_w (.clk(aclk), .rst(!aresetn), .s_valid(s_axi_wvalid), .s_ready(s_axi_wready),
        .s_data(w_in), .m_valid(m_axi_wvalid), .m_ready(m_axi_wready), .m_data(w_out));
    assign m_axi_wlast = w_out[0 +: 1];
    assign m_axi_wstrb = w_out[0 + (1) +: DATA_W/8];
    assign m_axi_wdata = w_out[0 + (1) + (DATA_W/8) +: DATA_W];
    // B channel: master port to slave port
    localparam int PW_B = (ID_W) + (2);
    wire [PW_B-1:0] b_in = {m_axi_bid, m_axi_bresp};
    wire [PW_B-1:0] b_out;
    pipe_reg_core #(.W(PW_B), .N(N), .MODE(MODE_B)) u_b (.clk(aclk), .rst(!aresetn), .s_valid(m_axi_bvalid), .s_ready(m_axi_bready),
        .s_data(b_in), .m_valid(s_axi_bvalid), .m_ready(s_axi_bready), .m_data(b_out));
    assign s_axi_bresp = b_out[0 +: 2];
    assign s_axi_bid = b_out[0 + (2) +: ID_W];
    // AR channel: slave port to master port
    localparam int PW_AR = (ID_W) + (ADDR_W) + (8) + (3) + (2) + (1) + (4) + (3) + (4);
    wire [PW_AR-1:0] ar_in = {s_axi_arid, s_axi_araddr, s_axi_arlen, s_axi_arsize, s_axi_arburst, s_axi_arlock, s_axi_arcache, s_axi_arprot, s_axi_arqos};
    wire [PW_AR-1:0] ar_out;
    pipe_reg_core #(.W(PW_AR), .N(N), .MODE(MODE_AR)) u_ar (.clk(aclk), .rst(!aresetn), .s_valid(s_axi_arvalid), .s_ready(s_axi_arready),
        .s_data(ar_in), .m_valid(m_axi_arvalid), .m_ready(m_axi_arready), .m_data(ar_out));
    assign m_axi_arqos = ar_out[0 +: 4];
    assign m_axi_arprot = ar_out[0 + (4) +: 3];
    assign m_axi_arcache = ar_out[0 + (4) + (3) +: 4];
    assign m_axi_arlock = ar_out[0 + (4) + (3) + (4) +: 1];
    assign m_axi_arburst = ar_out[0 + (4) + (3) + (4) + (1) +: 2];
    assign m_axi_arsize = ar_out[0 + (4) + (3) + (4) + (1) + (2) +: 3];
    assign m_axi_arlen = ar_out[0 + (4) + (3) + (4) + (1) + (2) + (3) +: 8];
    assign m_axi_araddr = ar_out[0 + (4) + (3) + (4) + (1) + (2) + (3) + (8) +: ADDR_W];
    assign m_axi_arid = ar_out[0 + (4) + (3) + (4) + (1) + (2) + (3) + (8) + (ADDR_W) +: ID_W];
    // R channel: master port to slave port
    localparam int PW_R = (ID_W) + (DATA_W) + (2) + (1);
    wire [PW_R-1:0] r_in = {m_axi_rid, m_axi_rdata, m_axi_rresp, m_axi_rlast};
    wire [PW_R-1:0] r_out;
    pipe_reg_core #(.W(PW_R), .N(N), .MODE(MODE_R)) u_r (.clk(aclk), .rst(!aresetn), .s_valid(m_axi_rvalid), .s_ready(m_axi_rready),
        .s_data(r_in), .m_valid(s_axi_rvalid), .m_ready(s_axi_rready), .m_data(r_out));
    assign s_axi_rlast = r_out[0 +: 1];
    assign s_axi_rresp = r_out[0 + (1) +: 2];
    assign s_axi_rdata = r_out[0 + (1) + (2) +: DATA_W];
    assign s_axi_rid = r_out[0 + (1) + (2) + (DATA_W) +: ID_W];
endmodule
