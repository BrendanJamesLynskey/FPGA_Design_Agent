// false_fire_tb: the two rule monitors driven directly by cocotb with legal but unusual traffic (axi_tx_false_fire_cocotb.py).
module false_fire_tb (
    input  logic        clk,
    input  logic        aresetn,
    input  logic [31:0] awaddr, input logic awvalid, input logic awready,
    input  logic [31:0] wdata,  input logic [3:0] wstrb, input logic wvalid, input logic wready,
    input  logic [1:0]  bresp,  input logic bvalid, input logic bready,
    input  logic [31:0] araddr, input logic arvalid, input logic arready,
    input  logic [31:0] rdata,  input logic [1:0] rresp, input logic rvalid, input logic rready,
    input  logic [31:0] tdata,  input logic [3:0] tkeep, input logic [3:0] tstrb, input logic tlast, input logic tvalid,
    input  logic        tready,
    output logic [9:0]  lviol,
    output logic [4:0]  sviol
);
    axil_rules u_l (.aclk(clk), .aresetn(aresetn), .awaddr(awaddr), .awprot(3'b0), .awvalid(awvalid), .awready(awready),
                    .wdata(wdata), .wstrb(wstrb), .wvalid(wvalid), .wready(wready), .bresp(bresp), .bvalid(bvalid),
                    .bready(bready), .araddr(araddr), .arprot(3'b0), .arvalid(arvalid), .arready(arready), .rdata(rdata),
                    .rresp(rresp), .rvalid(rvalid), .rready(rready), .viol(lviol));
    axis_rules u_s (.aclk(clk), .aresetn(aresetn), .maxlen(16'd0), .tdata(tdata), .tkeep(tkeep), .tstrb(tstrb), .tlast(tlast),
                    .tvalid(tvalid), .tready(tready), .viol(sviol));
endmodule
