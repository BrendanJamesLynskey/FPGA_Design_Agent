// b59a_axi_tx_top: the brief 59A board demonstration on the Nexys A7-100T. The UART test shell drives axi_tx_sys (the
// transactor, the protocol checkers, the scoreboard, our seeded-bug peripheral, the stream FIFO and the capture); target 0
// is AMD's AXI BRAM Controller (AXI4-Lite, 8 KB) with a Block Memory Generator; AMD's AXI Protocol Checker watches the same
// AXI4-Lite bus as a cross-check; the XADC is polled for the operating conditions.
// Window map (offsets from shell address 0x80): 0x00-0x3F axi_tx_sys (axi_tx/host/regs.py), and here:
//   0x40-0x4B XADC codes: temperature, VCCINT, VCCAUX, VCCBRAM; then their maximum and minimum since configuration
//   0x4C      alarm latch: [0] temperature [1] VCCINT [2] VCCAUX [3] VCCBRAM [4] over-temperature; write 1s to clear
//   0x50      AMD protocol checker: [0] pc_asserted;   0x51-0x55 pc_status[159:0], 32 bits each, low word first
// XADC alarm thresholds sit inside the Artix-7 -1 recommended operating conditions (knowledge bank
// artix7-speed-grade-limits: VCCINT 0.95-1.05 V, VCCAUX 1.71-1.89 V, VCCBRAM 0.95-1.05 V; board limit Tj 85 C):
// temperature 80 C (reset 75 C), VCCINT and VCCBRAM 0.96-1.04 V, VCCAUX 1.73-1.87 V (codes: UG480 transfer functions).
// LED0: a program is running. LED1: a protocol rule has fired since the last reset.
/* verilator lint_off UNUSEDSIGNAL */   // the read-select register keeps the whole address; the top bit chooses the range
module b59a_axi_tx_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic       CLK100MHZ,
    input  logic       CPU_RESETN,
    input  logic       UART_TXD_IN,
    output logic       UART_RXD_OUT,
    output logic [1:0] LED
);
    logic clk, rst;
    assign clk = CLK100MHZ;
    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;
    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES), .DESIGN_ID(32'h4158_5431),
                 .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    // ------------------------------------------------------------------ the transactor system
    logic [31:0] x_awaddr, x_wdata, x_araddr, x_rdata;
    logic [2:0]  x_awprot, x_arprot;
    logic [3:0]  x_wstrb;
    logic [1:0]  x_bresp, x_rresp;
    logic        x_awvalid, x_awready, x_wvalid, x_wready, x_bvalid, x_bready, x_arvalid, x_arready, x_rvalid, x_rready;
    logic [31:0] m_awaddr, m_wdata, m_araddr, m_rdata;
    logic [3:0]  m_wstrb;
    logic [1:0]  m_bresp, m_rresp;
    logic        m_awvalid, m_awready, m_wvalid, m_wready, m_bvalid, m_bready, m_arvalid, m_arready, m_rvalid, m_rready;
    logic        chk_trig, aresetn, running;
    logic [31:0] sys_q;
    axi_tx_sys u_sys (
        .clk(clk), .rst(rst), .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata),
        .win_rdata(sys_q), .ev_in(8'h00), .chk_trig(chk_trig), .aresetn(aresetn), .running(running),
        .x_awaddr(x_awaddr), .x_awprot(x_awprot), .x_awvalid(x_awvalid), .x_awready(x_awready), .x_wdata(x_wdata),
        .x_wstrb(x_wstrb), .x_wvalid(x_wvalid), .x_wready(x_wready), .x_bresp(x_bresp), .x_bvalid(x_bvalid),
        .x_bready(x_bready), .x_araddr(x_araddr), .x_arprot(x_arprot), .x_arvalid(x_arvalid), .x_arready(x_arready),
        .x_rdata(x_rdata), .x_rresp(x_rresp), .x_rvalid(x_rvalid), .x_rready(x_rready),
        .mon_awaddr(m_awaddr), .mon_awvalid(m_awvalid), .mon_awready(m_awready), .mon_wdata(m_wdata),
        .mon_wstrb(m_wstrb), .mon_wvalid(m_wvalid), .mon_wready(m_wready), .mon_bresp(m_bresp), .mon_bvalid(m_bvalid),
        .mon_bready(m_bready), .mon_araddr(m_araddr), .mon_arvalid(m_arvalid), .mon_arready(m_arready),
        .mon_rdata(m_rdata), .mon_rresp(m_rresp), .mon_rvalid(m_rvalid), .mon_rready(m_rready));

    // ------------------------------------------------------------------ target 0: AMD AXI BRAM Controller + Block Memory Generator
    logic        b_rst, b_clk, b_en;
    logic [3:0]  b_we;
    logic [12:0] b_addr;
    logic [31:0] b_wd, b_rd;
    /* verilator lint_off PINCONNECTEMPTY */
    amd_bram_ctrl u_bram_ctrl (
        .s_axi_aclk(clk), .s_axi_aresetn(aresetn),
        .s_axi_awaddr(x_awaddr[12:0]), .s_axi_awprot(x_awprot), .s_axi_awvalid(x_awvalid), .s_axi_awready(x_awready),
        .s_axi_wdata(x_wdata), .s_axi_wstrb(x_wstrb), .s_axi_wvalid(x_wvalid), .s_axi_wready(x_wready),
        .s_axi_bresp(x_bresp), .s_axi_bvalid(x_bvalid), .s_axi_bready(x_bready),
        .s_axi_araddr(x_araddr[12:0]), .s_axi_arprot(x_arprot), .s_axi_arvalid(x_arvalid), .s_axi_arready(x_arready),
        .s_axi_rdata(x_rdata), .s_axi_rresp(x_rresp), .s_axi_rvalid(x_rvalid), .s_axi_rready(x_rready),
        .bram_rst_a(b_rst), .bram_clk_a(b_clk), .bram_en_a(b_en), .bram_we_a(b_we), .bram_addr_a(b_addr),
        .bram_wrdata_a(b_wd), .bram_rddata_a(b_rd));
    amd_bram u_bram (
        .clka(b_clk), .rsta(b_rst), .ena(b_en), .wea(b_we), .addra({19'b0, b_addr}), .dina(b_wd), .douta(b_rd),
        .rsta_busy());

    // ------------------------------------------------------------------ cross-check: AMD AXI Protocol Checker on the same bus
    logic [159:0] pc_status;
    logic         pc_asserted;
    amd_axi_pc u_pc (
        .pc_status(pc_status), .pc_asserted(pc_asserted), .aclk(clk), .aresetn(aresetn),
        .pc_axi_awaddr(m_awaddr), .pc_axi_awprot(3'b000), .pc_axi_awvalid(m_awvalid), .pc_axi_awready(m_awready),
        .pc_axi_wdata(m_wdata), .pc_axi_wstrb(m_wstrb), .pc_axi_wvalid(m_wvalid), .pc_axi_wready(m_wready),
        .pc_axi_bresp(m_bresp), .pc_axi_bvalid(m_bvalid), .pc_axi_bready(m_bready),
        .pc_axi_araddr(m_araddr), .pc_axi_arprot(3'b000), .pc_axi_arvalid(m_arvalid), .pc_axi_arready(m_arready),
        .pc_axi_rdata(m_rdata), .pc_axi_rresp(m_rresp), .pc_axi_rvalid(m_rvalid), .pc_axi_rready(m_rready));

    // ------------------------------------------------------------------ XADC: conditions, min/max since configuration, alarms
    logic [15:0] do_x;
    logic        drdy, den = 1'b0;
    logic [6:0]  daddr = 7'h00;
    logic [7:0]  alm;
    logic        ot;
    logic [11:0] xcode [12];
    logic [3:0]  xsel = '0;
    logic [15:0] xpc = '0;
    logic [4:0]  alarms = '0;
    initial for (int i = 0; i < 12; i++) xcode[i] = '0;
    XADC #(
        .INIT_40(16'h1000), .INIT_41(16'h2EF0), .INIT_42(16'h0400), .INIT_48(16'h4700), .INIT_49(16'h0000),
        .INIT_4A(16'h4700), .INIT_4B(16'h0000), .INIT_4C(16'h0000), .INIT_4D(16'h0000), .INIT_4E(16'h0000),
        .INIT_4F(16'h0000), .INIT_50(16'hB360), .INIT_51(16'h58C0), .INIT_52(16'h9F90), .INIT_53(16'hCA33),
        .INIT_54(16'hB0E0), .INIT_55(16'h51F0), .INIT_56(16'h93A0), .INIT_57(16'hAE4E), .INIT_58(16'h58C0),
        .INIT_5C(16'h51F0), .SIM_DEVICE("7SERIES")
    ) u_xadc (
        .DCLK(clk), .DEN(den), .DWE(1'b0), .DADDR(daddr), .DI(16'h0000), .DO(do_x), .DRDY(drdy),
        .RESET(1'b0), .CONVST(1'b0), .CONVSTCLK(1'b0), .VP(1'b0), .VN(1'b0), .VAUXP(16'h0000), .VAUXN(16'h0000),
        .ALM(alm), .OT(ot), .BUSY(), .CHANNEL(), .EOC(), .EOS(), .JTAGBUSY(), .JTAGLOCKED(), .JTAGMODIFIED(), .MUXADDR());
    /* verilator lint_on PINCONNECTEMPTY */
    function automatic logic [6:0] xreg(input logic [3:0] k);
        case (k)
            4'd0: xreg = 7'h00;  4'd1: xreg = 7'h01;  4'd2: xreg = 7'h02;  4'd3: xreg = 7'h06;
            4'd4: xreg = 7'h20;  4'd5: xreg = 7'h21;  4'd6: xreg = 7'h22;  4'd7: xreg = 7'h23;
            4'd8: xreg = 7'h24;  4'd9: xreg = 7'h25;  4'd10: xreg = 7'h26; default: xreg = 7'h27;
        endcase
    endfunction
    wire alarm_clr = win_wr && win_addr == 7'h4C;
    always_ff @(posedge clk) begin
        den <= 1'b0;
        xpc <= xpc + 1'b1;
        if (xpc == '0) begin daddr <= xreg(xsel); den <= 1'b1; end
        if (drdy) begin xcode[xsel] <= do_x[15:4]; xsel <= (xsel == 4'd11) ? 4'd0 : xsel + 1'b1; end
        alarms <= (alarms & ~(alarm_clr ? win_wdata[4:0] : 5'h0)) | {ot, alm[3:0]};
    end

    // ------------------------------------------------------------------ LEDs, read mux (registered, like every block)
    logic viol_seen = 1'b0;
    always_ff @(posedge clk) begin
        if (rst) viol_seen <= 1'b0; else if (chk_trig) viol_seen <= 1'b1;
    end
    assign LED = {viol_seen, running};
    logic [6:0]  a_q = '0;
    logic [31:0] top_q = '0;
    always_ff @(posedge clk) begin
        a_q <= win_addr;
        casez (win_addr)
            7'h4C: top_q <= {27'b0, alarms};
            7'h50: top_q <= {31'b0, pc_asserted};
            7'h51: top_q <= pc_status[31:0];
            7'h52: top_q <= pc_status[63:32];
            7'h53: top_q <= pc_status[95:64];
            7'h54: top_q <= pc_status[127:96];
            7'h55: top_q <= pc_status[159:128];
            default: top_q <= (win_addr[6:4] == 3'h4 && win_addr[3:0] < 4'd12) ? {20'b0, xcode[win_addr[3:0]]} : 32'h0;
        endcase
    end
    assign win_rdata = (a_q[6] == 1'b0) ? sys_q : top_q;
    wire unused = &{1'b0, win_rd, alm[7:4], x_awaddr[31:13], x_araddr[31:13], do_x[3:0]};
endmodule
/* verilator lint_on UNUSEDSIGNAL */
