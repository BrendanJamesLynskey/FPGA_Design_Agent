// axil_xbar_tb.sv: the crossbar with brief 59's AXI4-Lite protocol checker (axi_tx/rtl/axil_checker.sv) on every
// link, N_M master-side and N_S slave-side. The masters and slaves themselves are Python models (cocotb_axil_xbar.py).
// chk_any[i] is sticky: link i broke an AXI4-Lite rule at least once (links 0..N_M-1 master side, then the slaves).
module axil_xbar_tb #(
    parameter int N_M    = 2,
    parameter int N_S    = 3,
    parameter int ADDR_W = 32,
    parameter logic [N_S*ADDR_W-1:0] S_BASE = '0,
    parameter logic [N_S*8-1:0]      S_BITS = {N_S{8'd12}}
) (
    input  logic                  clk,
    input  logic                  rst,
    input  logic [N_M*ADDR_W-1:0] s_axil_awaddr,
    input  logic [N_M*3-1:0]      s_axil_awprot,
    input  logic [N_M-1:0]        s_axil_awvalid,
    output logic [N_M-1:0]        s_axil_awready,
    input  logic [N_M*32-1:0]     s_axil_wdata,
    input  logic [N_M*4-1:0]      s_axil_wstrb,
    input  logic [N_M-1:0]        s_axil_wvalid,
    output logic [N_M-1:0]        s_axil_wready,
    output logic [N_M*2-1:0]      s_axil_bresp,
    output logic [N_M-1:0]        s_axil_bvalid,
    input  logic [N_M-1:0]        s_axil_bready,
    input  logic [N_M*ADDR_W-1:0] s_axil_araddr,
    input  logic [N_M*3-1:0]      s_axil_arprot,
    input  logic [N_M-1:0]        s_axil_arvalid,
    output logic [N_M-1:0]        s_axil_arready,
    output logic [N_M*32-1:0]     s_axil_rdata,
    output logic [N_M*2-1:0]      s_axil_rresp,
    output logic [N_M-1:0]        s_axil_rvalid,
    input  logic [N_M-1:0]        s_axil_rready,
    output logic [N_S*ADDR_W-1:0] m_axil_awaddr,
    output logic [N_S*3-1:0]      m_axil_awprot,
    output logic [N_S-1:0]        m_axil_awvalid,
    input  logic [N_S-1:0]        m_axil_awready,
    output logic [N_S*32-1:0]     m_axil_wdata,
    output logic [N_S*4-1:0]      m_axil_wstrb,
    output logic [N_S-1:0]        m_axil_wvalid,
    input  logic [N_S-1:0]        m_axil_wready,
    input  logic [N_S*2-1:0]      m_axil_bresp,
    input  logic [N_S-1:0]        m_axil_bvalid,
    output logic [N_S-1:0]        m_axil_bready,
    output logic [N_S*ADDR_W-1:0] m_axil_araddr,
    output logic [N_S*3-1:0]      m_axil_arprot,
    output logic [N_S-1:0]        m_axil_arvalid,
    input  logic [N_S-1:0]        m_axil_arready,
    input  logic [N_S*32-1:0]     m_axil_rdata,
    input  logic [N_S*2-1:0]      m_axil_rresp,
    input  logic [N_S-1:0]        m_axil_rvalid,
    output logic [N_S-1:0]        m_axil_rready,
    output logic [N_M+N_S-1:0]    chk_any
);
    axil_xbar #(.N_M(N_M), .N_S(N_S), .ADDR_W(ADDR_W), .S_BASE(S_BASE), .S_BITS(S_BITS)) dut (.*);

    logic [31:0] now = '0;
    always_ff @(posedge clk) now <= now + 1'b1;

    for (genvar m = 0; m < N_M; m++) begin : g_mchk
        axil_checker #(.ADDR_W(ADDR_W), .DATA_W(32)) u_chk (
            .aclk(clk), .aresetn(!rst), .clear(1'b0), .en(10'h3FF), .now(now),
            .awaddr(s_axil_awaddr[m*ADDR_W +: ADDR_W]), .awprot(s_axil_awprot[m*3 +: 3]),
            .awvalid(s_axil_awvalid[m]), .awready(s_axil_awready[m]),
            .wdata(s_axil_wdata[m*32 +: 32]), .wstrb(s_axil_wstrb[m*4 +: 4]), .wvalid(s_axil_wvalid[m]), .wready(s_axil_wready[m]),
            .bresp(s_axil_bresp[m*2 +: 2]), .bvalid(s_axil_bvalid[m]), .bready(s_axil_bready[m]),
            .araddr(s_axil_araddr[m*ADDR_W +: ADDR_W]), .arprot(s_axil_arprot[m*3 +: 3]),
            .arvalid(s_axil_arvalid[m]), .arready(s_axil_arready[m]),
            .rdata(s_axil_rdata[m*32 +: 32]), .rresp(s_axil_rresp[m*2 +: 2]), .rvalid(s_axil_rvalid[m]), .rready(s_axil_rready[m]),
            .viol(), .trig(), .any(chk_any[m]), .rd_sel(6'd0), .rd_data());
    end
    for (genvar s = 0; s < N_S; s++) begin : g_schk
        axil_checker #(.ADDR_W(ADDR_W), .DATA_W(32)) u_chk (
            .aclk(clk), .aresetn(!rst), .clear(1'b0), .en(10'h3FF), .now(now),
            .awaddr(m_axil_awaddr[s*ADDR_W +: ADDR_W]), .awprot(m_axil_awprot[s*3 +: 3]),
            .awvalid(m_axil_awvalid[s]), .awready(m_axil_awready[s]),
            .wdata(m_axil_wdata[s*32 +: 32]), .wstrb(m_axil_wstrb[s*4 +: 4]), .wvalid(m_axil_wvalid[s]), .wready(m_axil_wready[s]),
            .bresp(m_axil_bresp[s*2 +: 2]), .bvalid(m_axil_bvalid[s]), .bready(m_axil_bready[s]),
            .araddr(m_axil_araddr[s*ADDR_W +: ADDR_W]), .arprot(m_axil_arprot[s*3 +: 3]),
            .arvalid(m_axil_arvalid[s]), .arready(m_axil_arready[s]),
            .rdata(m_axil_rdata[s*32 +: 32]), .rresp(m_axil_rresp[s*2 +: 2]), .rvalid(m_axil_rvalid[s]), .rready(m_axil_rready[s]),
            .viol(), .trig(), .any(chk_any[N_M+s]), .rd_sel(6'd0), .rd_data());
    end
endmodule
