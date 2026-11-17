// zb_ctrl: the control plane of the ZedBoard design (brief 64B). One AXI4-Lite slave port from the Zynq PS GP0 master goes
// through our axil_xbar (ip_lib/axil_xbar) to eight 4 KB windows:
//   slave  base         what
//     0    0x40000000   zb_lat        latency probe (generated register block; counter, FIRE command, T_FIRE, T_ACK, interrupt)
//     1    0x40010000   zb_hole_okay  bus-error experiment block, unmapped: okay
//     2    0x40020000   zb_hole_slverr                          unmapped: slverr
//     3    0x40030000   zb_hole_split                           unmapped: split (the house default)
//     4    0x40040000   m_dma0        AXI DMA 0 register port (outside this module)  [chain 0: DMA to the HP0 port]
//     5    0x40050000   m_acc0        accelerator 0 register block (outside)
//     6    0x40060000   m_dma1        AXI DMA 1 register port (outside)             [chain 1: DMA to the ACP port]
//     7    0x40070000   m_acc1        accelerator 1 register block (outside)
// An address in 0x40000000-0x7FFFFFFF that is in none of the windows gets DECERR from the crossbar (read data 0). Within a
// 4 KB window the window's own block answers (a hole in a generated block: its `unmapped` setting; DMA: the AMD IP's own).
// Reset: aresetn, active low, synchronous (the crossbar's active-high rst is made from it here).
module zb_ctrl (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axil:m_dma0:m_acc0:m_dma1:m_acc1, ASSOCIATED_RESET aresetn" *)
    input  logic        aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  logic        aresetn,
    input logic [31:0] s_axil_awaddr,
    input logic [2:0] s_axil_awprot,
    input logic s_axil_awvalid,
    output logic s_axil_awready,
    input logic [31:0] s_axil_wdata,
    input logic [3:0] s_axil_wstrb,
    input logic s_axil_wvalid,
    output logic s_axil_wready,
    output logic [1:0] s_axil_bresp,
    output logic s_axil_bvalid,
    input logic s_axil_bready,
    input logic [31:0] s_axil_araddr,
    input logic [2:0] s_axil_arprot,
    input logic s_axil_arvalid,
    output logic s_axil_arready,
    output logic [31:0] s_axil_rdata,
    output logic [1:0] s_axil_rresp,
    output logic s_axil_rvalid,
    input logic s_axil_rready,
    output logic [9:0] m_dma0_awaddr,
    output logic [2:0] m_dma0_awprot,
    output logic m_dma0_awvalid,
    input logic m_dma0_awready,
    output logic [31:0] m_dma0_wdata,
    output logic [3:0] m_dma0_wstrb,
    output logic m_dma0_wvalid,
    input logic m_dma0_wready,
    input logic [1:0] m_dma0_bresp,
    input logic m_dma0_bvalid,
    output logic m_dma0_bready,
    output logic [9:0] m_dma0_araddr,
    output logic [2:0] m_dma0_arprot,
    output logic m_dma0_arvalid,
    input logic m_dma0_arready,
    input logic [31:0] m_dma0_rdata,
    input logic [1:0] m_dma0_rresp,
    input logic m_dma0_rvalid,
    output logic m_dma0_rready,
    output logic [11:0] m_acc0_awaddr,
    output logic [2:0] m_acc0_awprot,
    output logic m_acc0_awvalid,
    input logic m_acc0_awready,
    output logic [31:0] m_acc0_wdata,
    output logic [3:0] m_acc0_wstrb,
    output logic m_acc0_wvalid,
    input logic m_acc0_wready,
    input logic [1:0] m_acc0_bresp,
    input logic m_acc0_bvalid,
    output logic m_acc0_bready,
    output logic [11:0] m_acc0_araddr,
    output logic [2:0] m_acc0_arprot,
    output logic m_acc0_arvalid,
    input logic m_acc0_arready,
    input logic [31:0] m_acc0_rdata,
    input logic [1:0] m_acc0_rresp,
    input logic m_acc0_rvalid,
    output logic m_acc0_rready,
    output logic [9:0] m_dma1_awaddr,
    output logic [2:0] m_dma1_awprot,
    output logic m_dma1_awvalid,
    input logic m_dma1_awready,
    output logic [31:0] m_dma1_wdata,
    output logic [3:0] m_dma1_wstrb,
    output logic m_dma1_wvalid,
    input logic m_dma1_wready,
    input logic [1:0] m_dma1_bresp,
    input logic m_dma1_bvalid,
    output logic m_dma1_bready,
    output logic [9:0] m_dma1_araddr,
    output logic [2:0] m_dma1_arprot,
    output logic m_dma1_arvalid,
    input logic m_dma1_arready,
    input logic [31:0] m_dma1_rdata,
    input logic [1:0] m_dma1_rresp,
    input logic m_dma1_rvalid,
    output logic m_dma1_rready,
    output logic [11:0] m_acc1_awaddr,
    output logic [2:0] m_acc1_awprot,
    output logic m_acc1_awvalid,
    input logic m_acc1_awready,
    output logic [31:0] m_acc1_wdata,
    output logic [3:0] m_acc1_wstrb,
    output logic m_acc1_wvalid,
    input logic m_acc1_wready,
    input logic [1:0] m_acc1_bresp,
    input logic m_acc1_bvalid,
    output logic m_acc1_bready,
    output logic [11:0] m_acc1_araddr,
    output logic [2:0] m_acc1_arprot,
    output logic m_acc1_arvalid,
    input logic m_acc1_arready,
    input logic [31:0] m_acc1_rdata,
    input logic [1:0] m_acc1_rresp,
    input logic m_acc1_rvalid,
    output logic m_acc1_rready,
    output logic        irq_lat,
    output logic [7:0]  led
);
    localparam int N_S = 8;
    logic rst;
    always_ff @(posedge aclk) rst <= !aresetn;

    // crossbar master-side buses, one lane per slave
    logic [N_S*32-1:0] x_awaddr, x_araddr, x_wdata, x_rdata;
    logic [N_S*3-1:0]  x_awprot, x_arprot;
    logic [N_S*4-1:0]  x_wstrb;
    logic [N_S*2-1:0]  x_bresp, x_rresp;
    logic [N_S-1:0]    x_awvalid, x_awready, x_wvalid, x_wready, x_bvalid, x_bready, x_arvalid, x_arready, x_rvalid, x_rready;

    function automatic logic [N_S*32-1:0] bases();
        logic [N_S*32-1:0] b;
        for (int i = 0; i < N_S; i++) b[i*32 +: 32] = 32'h4000_0000 + i * 32'h0001_0000;
        return b;
    endfunction

    axil_xbar #(.N_M(1), .N_S(N_S), .ADDR_W(32), .S_BASE(bases()), .S_BITS({N_S{8'd12}})) u_xbar (
        .clk(aclk), .rst(rst),
        .s_axil_awaddr, .s_axil_awprot, .s_axil_awvalid, .s_axil_awready, .s_axil_wdata, .s_axil_wstrb, .s_axil_wvalid,
        .s_axil_wready, .s_axil_bresp, .s_axil_bvalid, .s_axil_bready, .s_axil_araddr, .s_axil_arprot, .s_axil_arvalid,
        .s_axil_arready, .s_axil_rdata, .s_axil_rresp, .s_axil_rvalid, .s_axil_rready,
        .m_axil_awaddr(x_awaddr), .m_axil_awprot(x_awprot), .m_axil_awvalid(x_awvalid), .m_axil_awready(x_awready),
        .m_axil_wdata(x_wdata), .m_axil_wstrb(x_wstrb), .m_axil_wvalid(x_wvalid), .m_axil_wready(x_wready),
        .m_axil_bresp(x_bresp), .m_axil_bvalid(x_bvalid), .m_axil_bready(x_bready),
        .m_axil_araddr(x_araddr), .m_axil_arprot(x_arprot), .m_axil_arvalid(x_arvalid), .m_axil_arready(x_arready),
        .m_axil_rdata(x_rdata), .m_axil_rresp(x_rresp), .m_axil_rvalid(x_rvalid), .m_axil_rready(x_rready));

    // ---- slave 0: the latency probe
    logic [31:0] cnt, t_fire, t_ack;
    logic        fire, done_set, done_q, done_o;
    logic [15:0] delay;
    logic [16:0] dly;
    logic        armed;
    zb_lat_regs u_lat (
        .aclk, .aresetn,
        .s_axil_awaddr(x_awaddr[11:0]), .s_axil_awprot(x_awprot[2:0]), .s_axil_awvalid(x_awvalid[0]), .s_axil_awready(x_awready[0]),
        .s_axil_wdata(x_wdata[31:0]), .s_axil_wstrb(x_wstrb[3:0]), .s_axil_wvalid(x_wvalid[0]), .s_axil_wready(x_wready[0]),
        .s_axil_bresp(x_bresp[1:0]), .s_axil_bvalid(x_bvalid[0]), .s_axil_bready(x_bready[0]),
        .s_axil_araddr(x_araddr[11:0]), .s_axil_arprot(x_arprot[2:0]), .s_axil_arvalid(x_arvalid[0]), .s_axil_arready(x_arready[0]),
        .s_axil_rdata(x_rdata[31:0]), .s_axil_rresp(x_rresp[1:0]), .s_axil_rvalid(x_rvalid[0]), .s_axil_rready(x_rready[0]),
        .cmd_fire_pulse_o(fire), .delay_clocks_o(delay), .now_value_i(cnt), .t_fire_value_i(t_fire), .t_ack_value_i(t_ack),
        .irq_status_done_set_i(done_set), .irq_status_done_o(done_o), .irq_enable_done_o(), .scratch_value_o(), .irq_o(irq_lat));
    always_ff @(posedge aclk) begin
        cnt <= aresetn ? cnt + 32'd1 : 32'd0;
        done_set <= 1'b0;
        done_q <= done_o;
        if (!aresetn) begin armed <= 1'b0; t_fire <= '0; t_ack <= '0; dly <= '0; end
        else begin
            if (fire) begin t_fire <= cnt; dly <= {1'b0, delay}; armed <= 1'b1; end
            else if (armed) begin
                if (dly == 17'd0) begin done_set <= 1'b1; armed <= 1'b0; end else dly <= dly - 17'd1;
            end
            if (done_q && !done_o) t_ack <= cnt;      // the clock after the clearing write committed
        end
    end

    assign led = {6'b0, irq_lat, cnt[26]};        // LD0: heartbeat (about 0.7 Hz), LD1: the latency probe's interrupt line

    // ---- slaves 1-3: the bus-error experiment blocks
    zb_hole_okay_regs u_h_okay (
        .aclk, .aresetn,
        .s_axil_awaddr(x_awaddr[1*32 +: 12]), .s_axil_awprot(x_awprot[1*3 +: 3]), .s_axil_awvalid(x_awvalid[1]), .s_axil_awready(x_awready[1]),
        .s_axil_wdata(x_wdata[1*32 +: 32]), .s_axil_wstrb(x_wstrb[1*4 +: 4]), .s_axil_wvalid(x_wvalid[1]), .s_axil_wready(x_wready[1]),
        .s_axil_bresp(x_bresp[1*2 +: 2]), .s_axil_bvalid(x_bvalid[1]), .s_axil_bready(x_bready[1]),
        .s_axil_araddr(x_araddr[1*32 +: 12]), .s_axil_arprot(x_arprot[1*3 +: 3]), .s_axil_arvalid(x_arvalid[1]), .s_axil_arready(x_arready[1]),
        .s_axil_rdata(x_rdata[1*32 +: 32]), .s_axil_rresp(x_rresp[1*2 +: 2]), .s_axil_rvalid(x_rvalid[1]), .s_axil_rready(x_rready[1]),
        .ctrl_value_o(), .scratch_value_o());
    zb_hole_slverr_regs u_h_slverr (
        .aclk, .aresetn,
        .s_axil_awaddr(x_awaddr[2*32 +: 12]), .s_axil_awprot(x_awprot[2*3 +: 3]), .s_axil_awvalid(x_awvalid[2]), .s_axil_awready(x_awready[2]),
        .s_axil_wdata(x_wdata[2*32 +: 32]), .s_axil_wstrb(x_wstrb[2*4 +: 4]), .s_axil_wvalid(x_wvalid[2]), .s_axil_wready(x_wready[2]),
        .s_axil_bresp(x_bresp[2*2 +: 2]), .s_axil_bvalid(x_bvalid[2]), .s_axil_bready(x_bready[2]),
        .s_axil_araddr(x_araddr[2*32 +: 12]), .s_axil_arprot(x_arprot[2*3 +: 3]), .s_axil_arvalid(x_arvalid[2]), .s_axil_arready(x_arready[2]),
        .s_axil_rdata(x_rdata[2*32 +: 32]), .s_axil_rresp(x_rresp[2*2 +: 2]), .s_axil_rvalid(x_rvalid[2]), .s_axil_rready(x_rready[2]),
        .ctrl_value_o(), .scratch_value_o());
    zb_hole_split_regs u_h_split (
        .aclk, .aresetn,
        .s_axil_awaddr(x_awaddr[3*32 +: 12]), .s_axil_awprot(x_awprot[3*3 +: 3]), .s_axil_awvalid(x_awvalid[3]), .s_axil_awready(x_awready[3]),
        .s_axil_wdata(x_wdata[3*32 +: 32]), .s_axil_wstrb(x_wstrb[3*4 +: 4]), .s_axil_wvalid(x_wvalid[3]), .s_axil_wready(x_wready[3]),
        .s_axil_bresp(x_bresp[3*2 +: 2]), .s_axil_bvalid(x_bvalid[3]), .s_axil_bready(x_bready[3]),
        .s_axil_araddr(x_araddr[3*32 +: 12]), .s_axil_arprot(x_arprot[3*3 +: 3]), .s_axil_arvalid(x_arvalid[3]), .s_axil_arready(x_arready[3]),
        .s_axil_rdata(x_rdata[3*32 +: 32]), .s_axil_rresp(x_rresp[3*2 +: 2]), .s_axil_rvalid(x_rvalid[3]), .s_axil_rready(x_rready[3]),
        .ctrl_value_o(), .scratch_value_o());

    // ---- slaves 4-7: pass-through to the outside (the AMD DMA register ports and the accelerator blocks)
    assign m_dma0_awaddr = x_awaddr[4*32 +: 10]; assign m_dma0_awprot = x_awprot[4*3 +: 3]; assign m_dma0_awvalid = x_awvalid[4]; assign x_awready[4] = m_dma0_awready;
    assign m_dma0_wdata = x_wdata[4*32 +: 32]; assign m_dma0_wstrb = x_wstrb[4*4 +: 4]; assign m_dma0_wvalid = x_wvalid[4]; assign x_wready[4] = m_dma0_wready;
    assign x_bresp[4*2 +: 2] = m_dma0_bresp; assign x_bvalid[4] = m_dma0_bvalid; assign m_dma0_bready = x_bready[4];
    assign m_dma0_araddr = x_araddr[4*32 +: 10]; assign m_dma0_arprot = x_arprot[4*3 +: 3]; assign m_dma0_arvalid = x_arvalid[4]; assign x_arready[4] = m_dma0_arready;
    assign x_rdata[4*32 +: 32] = m_dma0_rdata; assign x_rresp[4*2 +: 2] = m_dma0_rresp; assign x_rvalid[4] = m_dma0_rvalid; assign m_dma0_rready = x_rready[4];
    assign m_acc0_awaddr = x_awaddr[5*32 +: 12]; assign m_acc0_awprot = x_awprot[5*3 +: 3]; assign m_acc0_awvalid = x_awvalid[5]; assign x_awready[5] = m_acc0_awready;
    assign m_acc0_wdata = x_wdata[5*32 +: 32]; assign m_acc0_wstrb = x_wstrb[5*4 +: 4]; assign m_acc0_wvalid = x_wvalid[5]; assign x_wready[5] = m_acc0_wready;
    assign x_bresp[5*2 +: 2] = m_acc0_bresp; assign x_bvalid[5] = m_acc0_bvalid; assign m_acc0_bready = x_bready[5];
    assign m_acc0_araddr = x_araddr[5*32 +: 12]; assign m_acc0_arprot = x_arprot[5*3 +: 3]; assign m_acc0_arvalid = x_arvalid[5]; assign x_arready[5] = m_acc0_arready;
    assign x_rdata[5*32 +: 32] = m_acc0_rdata; assign x_rresp[5*2 +: 2] = m_acc0_rresp; assign x_rvalid[5] = m_acc0_rvalid; assign m_acc0_rready = x_rready[5];
    assign m_dma1_awaddr = x_awaddr[6*32 +: 10]; assign m_dma1_awprot = x_awprot[6*3 +: 3]; assign m_dma1_awvalid = x_awvalid[6]; assign x_awready[6] = m_dma1_awready;
    assign m_dma1_wdata = x_wdata[6*32 +: 32]; assign m_dma1_wstrb = x_wstrb[6*4 +: 4]; assign m_dma1_wvalid = x_wvalid[6]; assign x_wready[6] = m_dma1_wready;
    assign x_bresp[6*2 +: 2] = m_dma1_bresp; assign x_bvalid[6] = m_dma1_bvalid; assign m_dma1_bready = x_bready[6];
    assign m_dma1_araddr = x_araddr[6*32 +: 10]; assign m_dma1_arprot = x_arprot[6*3 +: 3]; assign m_dma1_arvalid = x_arvalid[6]; assign x_arready[6] = m_dma1_arready;
    assign x_rdata[6*32 +: 32] = m_dma1_rdata; assign x_rresp[6*2 +: 2] = m_dma1_rresp; assign x_rvalid[6] = m_dma1_rvalid; assign m_dma1_rready = x_rready[6];
    assign m_acc1_awaddr = x_awaddr[7*32 +: 12]; assign m_acc1_awprot = x_awprot[7*3 +: 3]; assign m_acc1_awvalid = x_awvalid[7]; assign x_awready[7] = m_acc1_awready;
    assign m_acc1_wdata = x_wdata[7*32 +: 32]; assign m_acc1_wstrb = x_wstrb[7*4 +: 4]; assign m_acc1_wvalid = x_wvalid[7]; assign x_wready[7] = m_acc1_wready;
    assign x_bresp[7*2 +: 2] = m_acc1_bresp; assign x_bvalid[7] = m_acc1_bvalid; assign m_acc1_bready = x_bready[7];
    assign m_acc1_araddr = x_araddr[7*32 +: 12]; assign m_acc1_arprot = x_arprot[7*3 +: 3]; assign m_acc1_arvalid = x_arvalid[7]; assign x_arready[7] = m_acc1_arready;
    assign x_rdata[7*32 +: 32] = m_acc1_rdata; assign x_rresp[7*2 +: 2] = m_acc1_rresp; assign x_rvalid[7] = m_acc1_rvalid; assign m_acc1_rready = x_rready[7];
endmodule
