// Board top: reset bridge, test shell, UDP endpoint.
module v2_e_udp_endpoint_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0,
    parameter logic [31:0] DESIGN_ID      = 32'h5545_5031,  // "UEP1", shell register 0x00
    parameter logic [31:0] ID_WORD        = 32'h5544_5031,  // device register R0
    parameter int          DEFAULT_PERIOD = 100,
    parameter int          MIN_PERIOD     = 4,
    parameter int          MAX_PAYLOAD    = 8
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [15:0] LED
);
    logic        rst;
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;

    reset_sync u_rst (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(DESIGN_ID), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    udp_endpoint #(
        .ID_WORD(ID_WORD), .DEFAULT_PERIOD(DEFAULT_PERIOD),
        .MIN_PERIOD(MIN_PERIOD), .MAX_PAYLOAD(MAX_PAYLOAD)
    ) u_ep (
        .clk(CLK100MHZ), .rst(rst),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata), .led(LED));
endmodule
