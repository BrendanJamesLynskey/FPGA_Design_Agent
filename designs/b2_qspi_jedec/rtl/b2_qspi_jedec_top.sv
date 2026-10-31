// b2_qspi_jedec_top.sv: board self-check for the Nexys A7-100T's configuration
// flash (S25FL128S or S25FL127S, depending on the board's build). It reads the
// JEDEC ID (command 9Fh) and nothing else: the opcode is a constant inside
// qspi_rdid, so no write, erase or register-write command can be sent.
// DESIGN_ID is "B2QF".
//
// SCK reaches the flash through the configuration clock pin (CCLK), which a
// design can drive only through STARTUPE2's USRCCLKO. WP# (DQ2) is held low and
// HOLD# (DQ3) high in single-bit SPI mode.

module b2_qspi_jedec_top #(
    parameter int          CLKS_PER_BIT   = 868,        // 115200 baud at 100 MHz
    parameter int          TIMEOUT_CYCLES = 100_000,    // 1 ms
    parameter int          HALF           = 50,         // SCK 1 MHz
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic       CLK100MHZ,
    input  logic       CPU_RESETN,
    input  logic       UART_TXD_IN,     // host -> FPGA
    output logic       UART_RXD_OUT,    // FPGA -> host
    output logic       QSPI_CSN,        // 4.7 kohm pull-up on the board
    // the master XDC's QSPI_DQ[0..3], split by direction in this single-bit SPI design
    output logic       QSPI_DQ0,        // to the flash (SI)
    input  logic       QSPI_DQ1,        // from the flash (SO)
    output logic       QSPI_DQ2,        // WP#
    output logic       QSPI_DQ3         // HOLD#
);
    logic        clk, rst, sck, dq1;
    logic        dq0;
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;

    assign clk = CLK100MHZ;

    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h4232_5146), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    assign QSPI_DQ0 = dq0;
    assign QSPI_DQ2 = 1'b0;             // WP# low: status-register writes stay locked (none are sent anyway)
    assign QSPI_DQ3 = 1'b1;             // HOLD# high: not paused

    sync2 u_sync (.clk(clk), .rst(rst), .d(QSPI_DQ1), .q(dq1));

    qspi_regs #(.HALF(HALF)) u_regs (
        .clk(clk), .rst(rst),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata),
        .sck(sck), .cs_n(QSPI_CSN), .dq0(dq0), .dq1(dq1));

    // CCLK after configuration: USRCCLKO drives it, USRCCLKTS = 0 enables the output.
    // DONE keeps its normal behaviour (USRDONETS = 1); no other function is used, and the
    // primitive's outputs (CFGCLK, CFGMCLK, EOS, PREQ) go nowhere.
    /* verilator lint_off UNUSEDSIGNAL */
    logic cfgclk_nc, cfgmclk_nc, eos_nc, preq_nc;
    /* verilator lint_on UNUSEDSIGNAL */
    STARTUPE2 #(.PROG_USR("FALSE"), .SIM_CCLK_FREQ(0.0)) u_startup (
        .CFGCLK(cfgclk_nc), .CFGMCLK(cfgmclk_nc), .EOS(eos_nc), .PREQ(preq_nc),
        .CLK(1'b0), .GSR(1'b0), .GTS(1'b0), .KEYCLEARB(1'b1), .PACK(1'b0),
        .USRCCLKO(sck), .USRCCLKTS(1'b0), .USRDONEO(1'b1), .USRDONETS(1'b1));
endmodule
