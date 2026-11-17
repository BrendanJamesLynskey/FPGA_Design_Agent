// Board top: command packet screener (CPS1) behind the UART test shell.
module v2_e_cmd_parser_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000_000,
    parameter logic [31:0] DESIGN_ID      = 32'h43505331,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [15:0] LED
);
    logic rst;
    reset_sync u_rst (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(DESIGN_ID), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    logic        byte_vld, byte_end, busy, done, have_seq;
    logic [7:0]  byte_data, g_type;
    logic [3:0]  cls;
    logic [15:0] g_seq, g_pay0, last_seq;
    logic [31:0] g_pay1;

    cps_core #(.TIMEOUT_CYCLES(TIMEOUT_CYCLES)) u_core (
        .clk(CLK100MHZ), .rst(rst), .byte_vld(byte_vld), .byte_data(byte_data), .byte_end(byte_end),
        .busy(busy), .done(done), .cls(cls), .g_type(g_type), .g_seq(g_seq), .g_pay0(g_pay0),
        .g_pay1(g_pay1), .last_seq(last_seq), .have_seq(have_seq));

    cps_regs u_regs (
        .clk(CLK100MHZ), .rst(rst), .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata),
        .byte_vld(byte_vld), .byte_data(byte_data), .byte_end(byte_end),
        .busy(busy), .done(done), .cls(cls), .g_type(g_type), .g_seq(g_seq), .g_pay0(g_pay0),
        .g_pay1(g_pay1), .last_seq(last_seq), .have_seq(have_seq), .led(LED));
endmodule
