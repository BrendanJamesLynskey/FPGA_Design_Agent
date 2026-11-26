// Board top: test shell + sequencer + 3x3 median block.
module c9_median3x3_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic CLK100MHZ,
    input  logic CPU_RESETN,
    input  logic UART_TXD_IN,
    output logic UART_RXD_OUT
);
    logic        rst;
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;
    logic        mv_in, mv_out;
    logic [71:0] mpix;
    logic [7:0]  mmed;
    logic        shell_tx;

    c9_rst_sync u_rst (.clk(CLK100MHZ), .rstn_async(CPU_RESETN), .rst(rst));

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h4D45444E), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(shell_tx),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    // closes the idle gaps the shell leaves between response bytes
    c9_uart_regap #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_regap (
        .clk(CLK100MHZ), .rst(rst), .rx_in(shell_tx), .tx_out(UART_RXD_OUT));

    c9_sequencer u_seq (
        .clk(CLK100MHZ), .rst(rst),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata),
        .med_valid_in(mv_in), .med_pix(mpix),
        .med_valid_out(mv_out), .med_median(mmed));

    c9_median3x3 u_med (
        .clk(CLK100MHZ), .rst(rst), .valid_in(mv_in), .pix(mpix),
        .valid_out(mv_out), .median(mmed));
endmodule
