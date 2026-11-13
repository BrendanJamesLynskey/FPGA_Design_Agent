// Port-list stubs for the block-design tests: AXI4, AXI4-Stream and interrupt interfaces that no ip_lib entry has yet.
// Only the headers are read (flow/blockdesign/hdl.py); the bodies tie outputs so the files also compile.
module axi4_mst #(parameter int ID_W = 4, parameter int DATA_W = 32) (
    input  logic              clk,
    input  logic              rst,
    output logic [ID_W-1:0]   m_axi_awid,
    output logic [31:0]       m_axi_awaddr,
    output logic [7:0]        m_axi_awlen,
    output logic              m_axi_awvalid,
    input  logic              m_axi_awready,
    output logic [DATA_W-1:0] m_axi_wdata,
    output logic              m_axi_wlast,
    output logic              m_axi_wvalid,
    input  logic              m_axi_wready,
    input  logic [ID_W-1:0]   m_axi_bid,
    input  logic [1:0]        m_axi_bresp,
    input  logic              m_axi_bvalid,
    output logic              m_axi_bready,
    output logic [ID_W-1:0]   m_axi_arid,
    output logic [31:0]       m_axi_araddr,
    output logic [7:0]        m_axi_arlen,
    output logic              m_axi_arvalid,
    input  logic              m_axi_arready,
    input  logic [ID_W-1:0]   m_axi_rid,
    input  logic [DATA_W-1:0] m_axi_rdata,
    input  logic [1:0]        m_axi_rresp,
    input  logic              m_axi_rlast,
    input  logic              m_axi_rvalid,
    output logic              m_axi_rready
);
endmodule

module axi4_slv #(parameter int ID_W = 4, parameter int DATA_W = 32) (
    input  logic              clk,
    input  logic              rst,
    input  logic [ID_W-1:0]   s_axi_awid,
    input  logic [15:0]       s_axi_awaddr,
    input  logic [7:0]        s_axi_awlen,
    input  logic              s_axi_awvalid,
    output logic              s_axi_awready,
    input  logic [DATA_W-1:0] s_axi_wdata,
    input  logic              s_axi_wlast,
    input  logic              s_axi_wvalid,
    output logic              s_axi_wready,
    output logic [ID_W-1:0]   s_axi_bid,
    output logic [1:0]        s_axi_bresp,
    output logic              s_axi_bvalid,
    input  logic              s_axi_bready,
    input  logic [ID_W-1:0]   s_axi_arid,
    input  logic [15:0]       s_axi_araddr,
    input  logic [7:0]        s_axi_arlen,
    input  logic              s_axi_arvalid,
    output logic              s_axi_arready,
    output logic [ID_W-1:0]   s_axi_rid,
    output logic [DATA_W-1:0] s_axi_rdata,
    output logic [1:0]        s_axi_rresp,
    output logic              s_axi_rlast,
    output logic              s_axi_rvalid,
    input  logic              s_axi_rready
);
endmodule

module axis_src #(parameter int W = 8) (
    input  logic         clk,
    input  logic         rst,
    output logic [W-1:0] m_axis_tdata,
    output logic         m_axis_tvalid,
    input  logic         m_axis_tready,
    output logic         m_axis_tlast,
    output logic         irq
);
endmodule

module axis_snk #(parameter int W = 8) (
    input  logic         clk,
    input  logic         rst_n,
    input  logic [W-1:0] s_axis_tdata,
    input  logic         s_axis_tvalid,
    output logic         s_axis_tready,
    input  logic         ext_irq,
    input  logic [7:0]   level
);
endmodule
