// b2_tmp_adt7420_top.sv: board self-check for the Nexys A7-100T's ADT7420
// temperature sensor (I2C address 0x4B). The host reads the sensor's ID and
// temperature registers through the test shell; the design only ever sets the
// register pointer and reads, so it cannot change the sensor's configuration.
// DESIGN_ID is "B2TS".

module b2_tmp_adt7420_top #(
    parameter int          CLKS_PER_BIT   = 868,        // 115200 baud at 100 MHz
    parameter int          TIMEOUT_CYCLES = 100_000,    // 1 ms
    parameter int          QUARTER        = 250,        // I2C SCL 100 kHz
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic CLK100MHZ,
    input  logic CPU_RESETN,
    input  logic UART_TXD_IN,     // host -> FPGA
    output logic UART_RXD_OUT,    // FPGA -> host
    inout  wire  TMP_SCL,         // open drain, 1 kohm pull-ups on the board
    inout  wire  TMP_SDA
);
    logic        clk, rst;
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;
    logic        scl_oe, sda_oe;
    logic [1:0]  lines;

    assign clk = CLK100MHZ;

    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h4232_5453), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    assign TMP_SCL = scl_oe ? 1'b0 : 1'bz;
    assign TMP_SDA = sda_oe ? 1'b0 : 1'bz;

    sync2 #(.WIDTH(2), .RESET_VALUE(2'b11)) u_sync (.clk(clk), .rst(rst), .d({TMP_SCL, TMP_SDA}), .q(lines));

    tmp_regs #(.QUARTER(QUARTER), .DEV_ADDR(7'h4B)) u_regs (
        .clk(clk), .rst(rst),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata),
        .scl_oe(scl_oe), .sda_oe(sda_oe), .scl_in(lines[1]), .sda_in(lines[0]));
endmodule
