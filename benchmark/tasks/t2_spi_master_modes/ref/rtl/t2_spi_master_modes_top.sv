// t2_spi_master_modes_top.sv: board top (Nexys A7-100T, master-XDC port names).
// Reference design for benchmark task t2_spi_master_modes; DESIGN_ID "SPIM".
// SPI master on Pmod JB: JB1 CS_N, JB2 MOSI, JB3 MISO, JB4 SCLK.
module t2_spi_master_modes_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic CLK100MHZ,
    input  logic CPU_RESETN,
    output logic JB1,
    output logic JB2,
    input  logic JB3,
    output logic JB4,
    input  logic UART_TXD_IN,
    output logic UART_RXD_OUT
);
    logic        clk, rst, win_wr, win_rd, miso;
    logic [6:0]  win_addr;
    logic [31:0] win_wdata, win_rdata;

    assign clk = CLK100MHZ;
    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h5350_494D), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    sync2 u_sync (.clk(clk), .rst(rst), .d(JB3), .q(miso));

    spim_regs u_regs (
        .clk(clk), .rst(rst), .miso_pin(miso), .cs_n(JB1), .sclk(JB4), .mosi(JB2),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));
endmodule
