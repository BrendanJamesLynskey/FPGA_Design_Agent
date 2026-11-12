// axil_checker: the AXI4-Lite rule monitor and its log as one block to place beside any AXI4-Lite interface (brief 59A):
// axil_rules + axi_viol_log. Port-only; trig pulses when a rule episode starts (a capture trigger).
module axil_checker #(
    parameter int ADDR_W = 32,
    parameter int DATA_W = 32
) (
    input  logic                aclk,
    input  logic                aresetn,
    input  logic                clear,
    input  logic [9:0]          en,
    input  logic [31:0]         now,
    input  logic [ADDR_W-1:0]   awaddr,
    input  logic [2:0]          awprot,
    input  logic                awvalid,
    input  logic                awready,
    input  logic [DATA_W-1:0]   wdata,
    input  logic [DATA_W/8-1:0] wstrb,
    input  logic                wvalid,
    input  logic                wready,
    input  logic [1:0]          bresp,
    input  logic                bvalid,
    input  logic                bready,
    input  logic [ADDR_W-1:0]   araddr,
    input  logic [2:0]          arprot,
    input  logic                arvalid,
    input  logic                arready,
    input  logic [DATA_W-1:0]   rdata,
    input  logic [1:0]          rresp,
    input  logic                rvalid,
    input  logic                rready,
    output logic [9:0]          viol,
    output logic                trig,
    output logic                any,
    input  logic [5:0]          rd_sel,
    output logic [31:0]         rd_data
);
    axil_rules #(.ADDR_W(ADDR_W), .DATA_W(DATA_W)) u_rules (
        .aclk(aclk), .aresetn(aresetn), .awaddr(awaddr), .awprot(awprot), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(wstrb), .wvalid(wvalid), .wready(wready), .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arprot(arprot), .arvalid(arvalid), .arready(arready), .rdata(rdata), .rresp(rresp),
        .rvalid(rvalid), .rready(rready), .viol(viol));
    axi_viol_log #(.NR(10)) u_log (.clk(aclk), .clear(clear), .en(en), .viol(viol), .now(now), .trig(trig), .any(any),
                                  .rd_sel(rd_sel), .rd_data(rd_data));
endmodule
