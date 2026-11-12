// axi_tx_sys: the brief 59A demonstration system around axi_tx_core, shared by the board top and the simulation:
//   - target 0: an external AXI4-Lite slave port (the board's AMD AXI BRAM Controller; axil_mem_model in simulation)
//   - target 1: axil_demo_periph (our peripheral, with its run-time seeded bugs)
//   - the stream DUT: axis_demo_fifo between the transactor's source and sink
//   - a capture: ip_lib/logic_analyser on the AXI4-Lite handshakes and the rule vector, triggered by a rule episode
// Window map (shell offsets 0x00-0x7F): 0x00-0x1F axi_tx_core, 0x20-0x2F logic analyser, 0x30 SYS_CTRL, 0x31 SYS_INFO;
// 0x40-0x7F are left to the board top (XADC, cross-check). The host's names for all of them: axi_tx/host/regs.py.
//   SYS_CTRL (RW): [0] target (0 external, 1 peripheral)  [6:4] peripheral bug  [9:8] stream DUT bug
//                  [12] hold the targets' reset (ARESETn low on both buses while 1)
// The target select is a static mux: change it only while no program runs.
/* verilator lint_off UNUSEDSIGNAL */   // the read-select register keeps the whole address; the top bits choose the block
module axi_tx_sys #(
    parameter int LCHK = 1,
    parameter int SCHK = 1,
    parameter int MON  = 1,
    parameter int LA_ADDR_W = 9
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,          // 0x00-0x3F; the top adds its own range
    input  logic [7:0]  ev_in,
    output logic        chk_trig,
    output logic        aresetn,
    output logic        running,
    // external target (target 0): AXI4-Lite master port
    output logic [31:0] x_awaddr,
    output logic [2:0]  x_awprot,
    output logic        x_awvalid,
    input  logic        x_awready,
    output logic [31:0] x_wdata,
    output logic [3:0]  x_wstrb,
    output logic        x_wvalid,
    input  logic        x_wready,
    input  logic [1:0]  x_bresp,
    input  logic        x_bvalid,
    output logic        x_bready,
    output logic [31:0] x_araddr,
    output logic [2:0]  x_arprot,
    output logic        x_arvalid,
    input  logic        x_arready,
    input  logic [31:0] x_rdata,
    input  logic [1:0]  x_rresp,
    input  logic        x_rvalid,
    output logic        x_rready,
    // the monitored AXI4-Lite bus, for a cross-check checker in the top
    output logic [31:0] mon_awaddr, output logic mon_awvalid, output logic mon_awready,
    output logic [31:0] mon_wdata,  output logic [3:0] mon_wstrb, output logic mon_wvalid, output logic mon_wready,
    output logic [1:0]  mon_bresp,  output logic mon_bvalid, output logic mon_bready,
    output logic [31:0] mon_araddr, output logic mon_arvalid, output logic mon_arready,
    output logic [31:0] mon_rdata,  output logic [1:0] mon_rresp, output logic mon_rvalid, output logic mon_rready
);
    logic [31:0] sys_ctrl = '0;
    always_ff @(posedge clk) begin
        if (rst) sys_ctrl <= '0;
        else if (win_wr && win_addr == 7'h30) sys_ctrl <= win_wdata & 32'h0000_1371;
    end
    wire       tsel = sys_ctrl[0];
    wire [2:0] lbug = sys_ctrl[6:4];
    wire [1:0] sbug = sys_ctrl[9:8];
    assign aresetn = !rst && !sys_ctrl[12];

    // ------------------------------------------------------------------ the transactor
    logic [31:0] awaddr, wdata, araddr, rdata;
    logic [2:0]  awprot, arprot;
    logic [3:0]  wstrb;
    logic [1:0]  bresp, rresp;
    logic        awvalid, awready, wvalid, wready, bvalid, bready, arvalid, arready, rvalid, rready;
    logic [31:0] st_d, sr_d;
    logic [3:0]  st_k, st_s, sr_k, sr_s;
    logic        st_l, st_v, st_r, sr_l, sr_v, sr_r;
    logic [9:0]  lviol;
    logic [4:0]  sviol;
    logic [31:0] core_q;
    axi_tx_core #(.SDATA_W(32), .LCHK(LCHK), .SCHK(SCHK), .MON(MON)) u_core (
        .clk(clk), .rst(rst), .aresetn(aresetn), .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(core_q), .ev_in(ev_in), .chk_trig(chk_trig), .lite_viol(lviol),
        .strm_viol(sviol), .running(running),
        .m_axil_awaddr(awaddr), .m_axil_awprot(awprot), .m_axil_awvalid(awvalid), .m_axil_awready(awready),
        .m_axil_wdata(wdata), .m_axil_wstrb(wstrb), .m_axil_wvalid(wvalid), .m_axil_wready(wready),
        .m_axil_bresp(bresp), .m_axil_bvalid(bvalid), .m_axil_bready(bready),
        .m_axil_araddr(araddr), .m_axil_arprot(arprot), .m_axil_arvalid(arvalid), .m_axil_arready(arready),
        .m_axil_rdata(rdata), .m_axil_rresp(rresp), .m_axil_rvalid(rvalid), .m_axil_rready(rready),
        .m_axis_tdata(st_d), .m_axis_tkeep(st_k), .m_axis_tstrb(st_s), .m_axis_tlast(st_l), .m_axis_tvalid(st_v),
        .m_axis_tready(st_r), .s_axis_tdata(sr_d), .s_axis_tkeep(sr_k), .s_axis_tstrb(sr_s), .s_axis_tlast(sr_l),
        .s_axis_tvalid(sr_v), .s_axis_tready(sr_r));

    // ------------------------------------------------------------------ targets
    logic        p_awready, p_wready, p_bvalid, p_arready, p_rvalid;
    logic [1:0]  p_bresp, p_rresp;
    logic [31:0] p_rdata;
    axil_demo_periph u_periph (
        .aclk(clk), .aresetn(aresetn), .bug_sel(lbug), .run_en(running),
        .s_awaddr(awaddr), .s_awprot(awprot), .s_awvalid(awvalid && tsel), .s_awready(p_awready),
        .s_wdata(wdata), .s_wstrb(wstrb), .s_wvalid(wvalid && tsel), .s_wready(p_wready),
        .s_bresp(p_bresp), .s_bvalid(p_bvalid), .s_bready(bready && tsel),
        .s_araddr(araddr), .s_arprot(arprot), .s_arvalid(arvalid && tsel), .s_arready(p_arready),
        .s_rdata(p_rdata), .s_rresp(p_rresp), .s_rvalid(p_rvalid), .s_rready(rready && tsel));
    assign x_awaddr = awaddr; assign x_awprot = awprot; assign x_awvalid = awvalid && !tsel;
    assign x_wdata = wdata;   assign x_wstrb = wstrb;   assign x_wvalid = wvalid && !tsel;
    assign x_bready = bready && !tsel;
    assign x_araddr = araddr; assign x_arprot = arprot; assign x_arvalid = arvalid && !tsel;
    assign x_rready = rready && !tsel;
    assign awready = tsel ? p_awready : x_awready;
    assign wready  = tsel ? p_wready  : x_wready;
    assign bvalid  = tsel ? p_bvalid  : x_bvalid;
    assign bresp   = tsel ? p_bresp   : x_bresp;
    assign arready = tsel ? p_arready : x_arready;
    assign rvalid  = tsel ? p_rvalid  : x_rvalid;
    assign rresp   = tsel ? p_rresp   : x_rresp;
    assign rdata   = tsel ? p_rdata   : x_rdata;

    axis_demo_fifo #(.DATA_W(32)) u_fifo (
        .aclk(clk), .aresetn(aresetn), .bug_sel(sbug),
        .s_tdata(st_d), .s_tkeep(st_k), .s_tstrb(st_s), .s_tlast(st_l), .s_tvalid(st_v), .s_tready(st_r),
        .m_tdata(sr_d), .m_tkeep(sr_k), .m_tstrb(sr_s), .m_tlast(sr_l), .m_tvalid(sr_v), .m_tready(sr_r));

    assign mon_awaddr = awaddr; assign mon_awvalid = awvalid; assign mon_awready = awready;
    assign mon_wdata = wdata; assign mon_wstrb = wstrb; assign mon_wvalid = wvalid; assign mon_wready = wready;
    assign mon_bresp = bresp; assign mon_bvalid = bvalid; assign mon_bready = bready;
    assign mon_araddr = araddr; assign mon_arvalid = arvalid; assign mon_arready = arready;
    assign mon_rdata = rdata; assign mon_rresp = rresp; assign mon_rvalid = rvalid; assign mon_rready = rready;

    // ------------------------------------------------------------------ capture around a violation (logic_analyser, window 0x20-0x2F)
    // sample bits: [31] trigger pulse, [30:21] Lite rule vector, [20:11] AWV AWR WV WR BV BR ARV ARR RV RR,
    //              [10:9] BRESP, [8:7] RRESP, [6:0] RDATA[6:0]   (axi_tx/host/regs.py CAPTURE_FIELDS)
    // the bus bits are registered once so that they line up with the registered trigger pulse: the trigger sample
    // shows the cycle in which the rule broke
    logic [30:0] cap_q = '0;
    always_ff @(posedge clk) cap_q <= {lviol, awvalid, awready, wvalid, wready, bvalid, bready, arvalid, arready, rvalid,
                                       rready, bresp, rresp, rdata[6:0]};
    wire [31:0] cap = {chk_trig, cap_q};
    logic [31:0] la_q;
    logic_analyser #(.WIDTH(32), .ADDR_W(LA_ADDR_W)) u_la (
        .clk(clk), .rst(rst), .sample(cap), .sample_en(1'b1),
        .win_addr({3'b0, win_addr[3:0]}), .win_wr(win_wr && win_addr[6:4] == 3'h2), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(la_q));

    // ------------------------------------------------------------------ read mux: every block's data is registered, so register the select too
    logic [6:0] a_q = '0;
    logic [31:0] sys_q = '0;
    always_ff @(posedge clk) begin
        a_q <= win_addr;
        case (win_addr)
            7'h30: sys_q <= sys_ctrl;
            7'h31: sys_q <= {28'b0, 1'(MON), 1'(SCHK), 1'(LCHK), 1'b1};
            default: sys_q <= '0;
        endcase
    end
    always_comb begin
        if (a_q[6:5] == 2'b00)      win_rdata = core_q;
        else if (a_q[6:4] == 3'h2)  win_rdata = la_q;
        else if (a_q[6:4] == 3'h3)  win_rdata = sys_q;
        else                        win_rdata = '0;
    end
    wire unused = &{1'b0, sviol, st_s[0]};
endmodule
/* verilator lint_on UNUSEDSIGNAL */
