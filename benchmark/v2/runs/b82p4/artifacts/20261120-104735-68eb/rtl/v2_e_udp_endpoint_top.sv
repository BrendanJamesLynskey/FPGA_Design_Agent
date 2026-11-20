// Board top: reset and UART input synchronisers, test shell, endpoint core.
module v2_e_udp_endpoint_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [15:0] LED
);
    logic rst;          // active high, synchronous release
    logic rx_sync;
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;

    // Async assert, synchronous release; output is active high.
    reset_sync u_rst_sync (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

    // UART input is asynchronous to the clock; idle level is high.
    sync2 #(.WIDTH(1), .RESET_VALUE(1'b1)) u_rx_sync (
        .clk(CLK100MHZ), .rst(rst), .d(UART_TXD_IN), .q(rx_sync)
    );

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h55455031), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(rx_sync), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata)
    );

    uep_core u_core (
        .clk(CLK100MHZ), .rst(rst),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata), .led(LED)
    );
endmodule
