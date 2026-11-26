// chk_top: YOUR instance of the fast-convolution block with the protocol checkers beside it (arith brief 161; the runner defines DUT_MODULE and DUT_PARAMS). The error counts are chk_s_errs and
// chk_m_errs (AXI4-Stream rules on the two streams) and chk_l_errs (AXI4-Lite rules on the register interface).
`include "dut_defs.svh"
module chk_top #(
    parameter int LOGN = 8, parameter int L = 33, parameter int W = 16, parameter int TW = 18, parameter int WH = 24, parameter int FH = 14, parameter int GB = 1, parameter int RND = 1,
    parameter int CMUL = 4, parameter int TWSTAGES = 1, parameter int MULSTAGES = 2
) (
    input  logic                clk,
    input  logic                aresetn,
    input  logic                s_axis_tvalid,
    input  logic [2*W-1:0]      s_axis_tdata,
    output logic                s_axis_tready,
    input  logic                m_axis_tready,
    output logic                m_axis_tvalid,
    output logic [2*W-1:0]      m_axis_tdata,
    input  logic                s_axil_awvalid,
    output logic                s_axil_awready,
    input  logic [5:0]          s_axil_awaddr,
    input  logic                s_axil_wvalid,
    output logic                s_axil_wready,
    input  logic [31:0]         s_axil_wdata,
    input  logic [3:0]          s_axil_wstrb,
    output logic                s_axil_bvalid,
    input  logic                s_axil_bready,
    output logic [1:0]          s_axil_bresp,
    input  logic                s_axil_arvalid,
    output logic                s_axil_arready,
    input  logic [5:0]          s_axil_araddr,
    output logic                s_axil_rvalid,
    input  logic                s_axil_rready,
    output logic [31:0]         s_axil_rdata,
    output logic [1:0]          s_axil_rresp,
    output int                  chk_s_errs,
    output int                  chk_m_errs,
    output int                  chk_l_errs
);
    `DUT_MODULE `DUT_PARAMS u_dut (.clk, .aresetn, .s_axis_tvalid, .s_axis_tdata, .s_axis_tready, .m_axis_tready, .m_axis_tvalid, .m_axis_tdata,
        .s_axil_awvalid, .s_axil_awready, .s_axil_awaddr, .s_axil_wvalid, .s_axil_wready, .s_axil_wdata, .s_axil_wstrb, .s_axil_bvalid, .s_axil_bready, .s_axil_bresp,
        .s_axil_arvalid, .s_axil_arready, .s_axil_araddr, .s_axil_rvalid, .s_axil_rready, .s_axil_rdata, .s_axil_rresp);
    axis_checker #(.DW(2 * W), .NBEAT(0), .NO_STALL(0), .CONTIG(0), .NAME("fft_fastconv s_axis")) u_chk_s (.clk, .aresetn, .tvalid(s_axis_tvalid), .tready(s_axis_tready), .tdata(s_axis_tdata), .tlast(1'b0), .errs(chk_s_errs));
    axis_checker #(.DW(2 * W), .NBEAT(0), .NO_STALL(0), .CONTIG(0), .NAME("fft_fastconv m_axis")) u_chk_m (.clk, .aresetn, .tvalid(m_axis_tvalid), .tready(m_axis_tready), .tdata(m_axis_tdata), .tlast(1'b0), .errs(chk_m_errs));
    axil_checker #(.NAME("fft_fastconv s_axil")) u_chk_l (.clk, .aresetn, .awvalid(s_axil_awvalid), .awready(s_axil_awready), .awaddr(s_axil_awaddr), .wvalid(s_axil_wvalid), .wready(s_axil_wready), .wdata(s_axil_wdata), .wstrb(s_axil_wstrb),
        .bvalid(s_axil_bvalid), .bready(s_axil_bready), .bresp(s_axil_bresp), .arvalid(s_axil_arvalid), .arready(s_axil_arready), .araddr(s_axil_araddr), .rvalid(s_axil_rvalid), .rready(s_axil_rready),
        .rdata(s_axil_rdata), .rresp(s_axil_rresp), .errs(chk_l_errs));
endmodule
