// axi_tx_tb: the simulation top of brief 59A: axi_tx_sys with axil_mem_model as target 0 (the board has the AMD AXI BRAM
// Controller there), driven through the shell window by the same host code as the board (axi_tx/host/host.py).
module axi_tx_tb #(
    parameter int MEM_BUG = 0
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    input  logic [7:0]  ev_in
);
    logic [31:0] awaddr, wdata, araddr, rdata;
    logic [2:0]  awprot, arprot;
    logic [3:0]  wstrb;
    logic [1:0]  bresp, rresp;
    logic        awvalid, awready, wvalid, wready, bvalid, bready, arvalid, arready, rvalid, rready, aresetn;
    logic        chk_trig, running;
    axi_tx_sys u_sys (
        .clk(clk), .rst(rst), .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata),
        .win_rdata(win_rdata), .ev_in(ev_in), .chk_trig(chk_trig), .aresetn(aresetn), .running(running),
        .x_awaddr(awaddr), .x_awprot(awprot), .x_awvalid(awvalid), .x_awready(awready), .x_wdata(wdata), .x_wstrb(wstrb),
        .x_wvalid(wvalid), .x_wready(wready), .x_bresp(bresp), .x_bvalid(bvalid), .x_bready(bready), .x_araddr(araddr),
        .x_arprot(arprot), .x_arvalid(arvalid), .x_arready(arready), .x_rdata(rdata), .x_rresp(rresp), .x_rvalid(rvalid),
        .x_rready(rready),
        .mon_awaddr(), .mon_awvalid(), .mon_awready(), .mon_wdata(), .mon_wstrb(), .mon_wvalid(), .mon_wready(),
        .mon_bresp(), .mon_bvalid(), .mon_bready(), .mon_araddr(), .mon_arvalid(), .mon_arready(), .mon_rdata(),
        .mon_rresp(), .mon_rvalid(), .mon_rready());
    axil_mem_model #(.AW_WORDS(11), .BUG(MEM_BUG)) u_mem (
        .aclk(clk), .aresetn(aresetn), .s_awaddr(awaddr), .s_awprot(awprot), .s_awvalid(awvalid), .s_awready(awready),
        .s_wdata(wdata), .s_wstrb(wstrb), .s_wvalid(wvalid), .s_wready(wready), .s_bresp(bresp), .s_bvalid(bvalid),
        .s_bready(bready), .s_araddr(araddr), .s_arprot(arprot), .s_arvalid(arvalid), .s_arready(arready),
        .s_rdata(rdata), .s_rresp(rresp), .s_rvalid(rvalid), .s_rready(rready));
endmodule
