// Board top: reset synchroniser, test shell, register block, arithmetic core.
module c14_int8_dot_requant_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100000000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic       CLK100MHZ,
    input  logic       CPU_RESETN,
    input  logic       UART_TXD_IN,
    output logic       UART_RXD_OUT,
    output logic [0:0] LED
);
    localparam logic [31:0] DESIGN_ID = 32'h444F5451;  // "DOTQ"

    logic        rst;
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;
    logic        go, done, ready, relu;
    logic [63:0] act, wgt;
    logic [31:0] bias, acc;
    logic [15:0] mult;
    logic [4:0]  shift;
    logic [7:0]  y;
    logic        LED0;

    reset_sync u_rst (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(DESIGN_ID), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    dotq_regs u_regs (
        .clk(CLK100MHZ), .rst(rst),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata),
        .go(go), .act(act), .wgt(wgt), .bias(bias), .mult(mult),
        .shift(shift), .relu(relu), .done(done), .y(y), .acc(acc), .ready(ready));

    dotq_core u_core (
        .clk(CLK100MHZ), .rst(rst), .go(go), .act(act), .wgt(wgt), .bias(bias),
        .mult(mult), .shift(shift), .relu(relu), .done(done), .y(y), .acc(acc));

    // LED0 (spec name) is the ready flag; LED is the master-XDC bus, bit 0 only.
    assign LED0   = ready;
    assign LED[0] = LED0;
endmodule
