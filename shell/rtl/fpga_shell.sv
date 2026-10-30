// fpga_shell.sv: the reusable on-board test shell. A design embeds one of
// these, connects the board's USB-UART pins and maps its own registers into
// the window (addresses 0x80-0xFF). See shell/PROTOCOL.md for the protocol.

module fpga_shell #(
    parameter int          CLKS_PER_BIT   = 868,       // 100 MHz / 115200 baud
    parameter int          TIMEOUT_CYCLES = 100_000,   // 1 ms at 100 MHz
    parameter logic [31:0] DESIGN_ID      = 32'h0,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic        clk,
    input  logic        rst,          // synchronous, active high
    input  logic        uart_rx,      // from the host (asynchronous)
    output logic        uart_tx,      // to the host
    output logic [6:0]  win_addr,
    output logic        win_wr,
    output logic        win_rd,
    output logic [31:0] win_wdata,
    input  logic [31:0] win_rdata     // due one cycle after win_rd
);
    logic       rx_valid, rx_frame_err, tx_start, tx_busy;
    logic [7:0] rx_data, tx_data;

    uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_rx (
        .clk(clk), .rst(rst), .rx(uart_rx),
        .valid(rx_valid), .data(rx_data), .frame_err(rx_frame_err));

    uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_tx (
        .clk(clk), .rst(rst), .start(tx_start), .data(tx_data),
        .busy(tx_busy), .tx(uart_tx));

    shell_core #(
        .TIMEOUT_CYCLES(TIMEOUT_CYCLES), .DESIGN_ID(DESIGN_ID), .BUILD_STAMP(BUILD_STAMP)
    ) u_core (
        .clk(clk), .rst(rst),
        .rx_valid(rx_valid), .rx_data(rx_data), .rx_frame_err(rx_frame_err),
        .tx_start(tx_start), .tx_data(tx_data), .tx_busy(tx_busy),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));
endmodule
