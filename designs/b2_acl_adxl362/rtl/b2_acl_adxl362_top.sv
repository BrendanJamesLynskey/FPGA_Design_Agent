// b2_acl_adxl362_top.sv: board self-check for the Nexys A7-100T's ADXL362
// accelerometer (SPI mode 0). The host sends SPI transfers (read the ID
// registers, start measurement, read a sample, back to standby) through the
// test shell. DESIGN_ID is "B2AC".

module b2_acl_adxl362_top #(
    parameter int          CLKS_PER_BIT   = 868,        // 115200 baud at 100 MHz
    parameter int          TIMEOUT_CYCLES = 100_000,    // 1 ms
    parameter int          HALF           = 50,         // SPI SCLK 1 MHz (the RM recommends 1-5 MHz)
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic CLK100MHZ,
    input  logic CPU_RESETN,
    input  logic UART_TXD_IN,     // host -> FPGA
    output logic UART_RXD_OUT,    // FPGA -> host
    output logic ACL_SCLK,
    output logic ACL_MOSI,
    output logic ACL_CSN,         // 1 kohm pull-up on the board
    input  logic ACL_MISO
);
    logic        clk, rst, miso;
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;

    assign clk = CLK100MHZ;

    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h4232_4143), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    sync2 u_sync (.clk(clk), .rst(rst), .d(ACL_MISO), .q(miso));

    acl_regs #(.HALF(HALF)) u_regs (
        .clk(clk), .rst(rst),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata),
        .sclk(ACL_SCLK), .mosi(ACL_MOSI), .cs_n(ACL_CSN), .miso(miso));
endmodule
