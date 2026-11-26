// axil_reg_slice.sv: an AXI4-Lite register slice for all five channels (AW, W, B, AR, R), one pipe_reg_core chain per channel
// (brief 151; owner 2026-11-21: favour AMBA AXI). Each channel has its own MODE (0 FWD, 1 SKID, 2 FULL, 3 HALF, 4 COMB; see
// ip_lib/pipe_reg) and all channels have N slices in series. Channels are independent: this block does not reorder or couple
// them, so every AXI4-Lite ordering rule between channels is the ones the endpoints already keep. Payload signals are the
// AXI4-Lite ones (awaddr/awprot, wdata/wstrb, bresp, araddr/arprot, rdata/rresp); aresetn active low, synchronous. A channel with
// MODE 4 or 0 has a combinational ready path from the other port; the other modes do not.
// Not carried: nothing is dropped. Compare with AMD's AXI Register Slice: ip_lib/pipe_reg/DATASHEET.md, "Against the vendor".
module axil_reg_slice #(
    parameter int ADDR_W = 32,
    parameter int DATA_W = 32,
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
    input  logic [ADDR_W-1:0] s_axi_awaddr,
    input  logic [3-1:0] s_axi_awprot,
    output logic m_axi_awvalid,
    input  logic m_axi_awready,
    output logic [ADDR_W-1:0] m_axi_awaddr,
    output logic [3-1:0] m_axi_awprot,
    input  logic s_axi_wvalid,
    output logic s_axi_wready,
    input  logic [DATA_W-1:0] s_axi_wdata,
    input  logic [DATA_W/8-1:0] s_axi_wstrb,
    output logic m_axi_wvalid,
    input  logic m_axi_wready,
    output logic [DATA_W-1:0] m_axi_wdata,
    output logic [DATA_W/8-1:0] m_axi_wstrb,
    output logic s_axi_bvalid,
    input  logic s_axi_bready,
    output logic [2-1:0] s_axi_bresp,
    input  logic m_axi_bvalid,
    output logic m_axi_bready,
    input  logic [2-1:0] m_axi_bresp,
    input  logic s_axi_arvalid,
    output logic s_axi_arready,
    input  logic [ADDR_W-1:0] s_axi_araddr,
    input  logic [3-1:0] s_axi_arprot,
    output logic m_axi_arvalid,
    input  logic m_axi_arready,
    output logic [ADDR_W-1:0] m_axi_araddr,
    output logic [3-1:0] m_axi_arprot,
    output logic s_axi_rvalid,
    input  logic s_axi_rready,
    output logic [DATA_W-1:0] s_axi_rdata,
    output logic [2-1:0] s_axi_rresp,
    input  logic m_axi_rvalid,
    output logic m_axi_rready,
    input  logic [DATA_W-1:0] m_axi_rdata,
    input  logic [2-1:0] m_axi_rresp
);
    // AW channel: slave port to master port
    localparam int PW_AW = (ADDR_W) + (3);
    wire [PW_AW-1:0] aw_in = {s_axi_awaddr, s_axi_awprot};
    wire [PW_AW-1:0] aw_out;
    pipe_reg_core #(.W(PW_AW), .N(N), .MODE(MODE_AW)) u_aw (.clk(aclk), .rst(!aresetn), .s_valid(s_axi_awvalid), .s_ready(s_axi_awready),
        .s_data(aw_in), .m_valid(m_axi_awvalid), .m_ready(m_axi_awready), .m_data(aw_out));
    assign m_axi_awprot = aw_out[0 +: 3];
    assign m_axi_awaddr = aw_out[0 + (3) +: ADDR_W];
    // W channel: slave port to master port
    localparam int PW_W = (DATA_W) + (DATA_W/8);
    wire [PW_W-1:0] w_in = {s_axi_wdata, s_axi_wstrb};
    wire [PW_W-1:0] w_out;
    pipe_reg_core #(.W(PW_W), .N(N), .MODE(MODE_W)) u_w (.clk(aclk), .rst(!aresetn), .s_valid(s_axi_wvalid), .s_ready(s_axi_wready),
        .s_data(w_in), .m_valid(m_axi_wvalid), .m_ready(m_axi_wready), .m_data(w_out));
    assign m_axi_wstrb = w_out[0 +: DATA_W/8];
    assign m_axi_wdata = w_out[0 + (DATA_W/8) +: DATA_W];
    // B channel: master port to slave port
    localparam int PW_B = (2);
    wire [PW_B-1:0] b_in = {m_axi_bresp};
    wire [PW_B-1:0] b_out;
    pipe_reg_core #(.W(PW_B), .N(N), .MODE(MODE_B)) u_b (.clk(aclk), .rst(!aresetn), .s_valid(m_axi_bvalid), .s_ready(m_axi_bready),
        .s_data(b_in), .m_valid(s_axi_bvalid), .m_ready(s_axi_bready), .m_data(b_out));
    assign s_axi_bresp = b_out[0 +: 2];
    // AR channel: slave port to master port
    localparam int PW_AR = (ADDR_W) + (3);
    wire [PW_AR-1:0] ar_in = {s_axi_araddr, s_axi_arprot};
    wire [PW_AR-1:0] ar_out;
    pipe_reg_core #(.W(PW_AR), .N(N), .MODE(MODE_AR)) u_ar (.clk(aclk), .rst(!aresetn), .s_valid(s_axi_arvalid), .s_ready(s_axi_arready),
        .s_data(ar_in), .m_valid(m_axi_arvalid), .m_ready(m_axi_arready), .m_data(ar_out));
    assign m_axi_arprot = ar_out[0 +: 3];
    assign m_axi_araddr = ar_out[0 + (3) +: ADDR_W];
    // R channel: master port to slave port
    localparam int PW_R = (DATA_W) + (2);
    wire [PW_R-1:0] r_in = {m_axi_rdata, m_axi_rresp};
    wire [PW_R-1:0] r_out;
    pipe_reg_core #(.W(PW_R), .N(N), .MODE(MODE_R)) u_r (.clk(aclk), .rst(!aresetn), .s_valid(m_axi_rvalid), .s_ready(m_axi_rready),
        .s_data(r_in), .m_valid(s_axi_rvalid), .m_ready(s_axi_rready), .m_data(r_out));
    assign s_axi_rresp = r_out[0 +: 2];
    assign s_axi_rdata = r_out[0 + (2) +: DATA_W];
endmodule
