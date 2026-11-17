// v2_e_cmd_parser_top: board top of the command packet screener (CPS1).
module v2_e_cmd_parser_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter logic [31:0] DESIGN_ID      = 32'h43505331,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
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

    logic        byte_valid;
    logic [8:0]  byte_data;
    logic [3:0]  result;
    logic [7:0]  ptype;
    logic [15:0] pseq, pay0, last_seq;
    logic [31:0] pay1;
    logic        have, busy;
    logic [111:0] ctrs;

    rst_sync u_rst (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(DESIGN_ID), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    reg_map u_regs (
        .clk(CLK100MHZ), .rst(rst),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata),
        .byte_valid(byte_valid), .byte_out(byte_data),
        .result(result), .ptype(ptype), .pseq(pseq), .pay0(pay0), .pay1(pay1),
        .last_seq(last_seq), .have(have), .busy(busy), .ctrs(ctrs));

    cps_core u_core (
        .clk(CLK100MHZ), .rst(rst),
        .byte_valid(byte_valid), .byte_in(byte_data),
        .result(result), .ptype(ptype), .pseq(pseq), .pay0(pay0), .pay1(pay1),
        .last_seq(last_seq), .have(have), .busy(busy), .ctrs(ctrs));

    assign LED = {last_seq[7:0], ctrs[7:0]};
endmodule
