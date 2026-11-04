// t2_qspi_sfdp_top.sv: board top (Nexys A7-100T, master-XDC port names).
// Reference design for benchmark task t2_qspi_sfdp; DESIGN_ID "SFDP".
// Reads the configuration flash's JEDEC ID and SFDP header. SCK leaves through
// STARTUPE2 USRCCLKO; WP# (DQ2) low, HOLD# (DQ3) high; single-bit SPI mode 0.
module t2_qspi_sfdp_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter int          HALF           = 10,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic CLK100MHZ,
    input  logic CPU_RESETN,
    output logic QSPI_CSN,
    output logic QSPI_DQ0,
    input  logic QSPI_DQ1,
    output logic QSPI_DQ2,
    output logic QSPI_DQ3,
    input  logic UART_TXD_IN,
    output logic UART_RXD_OUT
);
    logic        clk, rst, win_wr, win_rd, miso, sck;
    logic [6:0]  win_addr;
    logic [31:0] win_wdata, win_rdata;

    assign clk = CLK100MHZ;
    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h5346_4450), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    sync2 u_sync (.clk(clk), .rst(rst), .d(QSPI_DQ1), .q(miso));

    assign QSPI_DQ2 = 1'b0;
    assign QSPI_DQ3 = 1'b1;

    sfdp_ctl #(.HALF(HALF)) u_ctl (
        .clk(clk), .rst(rst), .miso(miso), .sck(sck), .mosi(QSPI_DQ0), .csn(QSPI_CSN),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    /* verilator lint_off UNUSEDSIGNAL */
    logic cfgclk_nc, cfgmclk_nc, eos_nc, preq_nc;
    /* verilator lint_on UNUSEDSIGNAL */
    STARTUPE2 #(.PROG_USR("FALSE"), .SIM_CCLK_FREQ(0.0)) u_startup (
        .CFGCLK(cfgclk_nc), .CFGMCLK(cfgmclk_nc), .EOS(eos_nc), .PREQ(preq_nc),
        .CLK(1'b0), .GSR(1'b0), .GTS(1'b0), .KEYCLEARB(1'b1), .PACK(1'b0),
        .USRCCLKO(sck), .USRCCLKTS(1'b0), .USRDONEO(1'b1), .USRDONETS(1'b1));
endmodule
