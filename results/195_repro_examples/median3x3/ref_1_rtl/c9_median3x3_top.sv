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
    logic rst;
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;
    logic        pix_valid, med_valid;
    logic [71:0] pix;
    logic [7:0]  med;

    reset_sync u_rst (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h4D45444E), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    sequencer u_seq (
        .clk(CLK100MHZ), .rst(rst),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata),
        .pix_valid(pix_valid), .pix(pix), .med(med), .med_valid(med_valid));

    median3x3 u_med (
        .clk(CLK100MHZ), .rst(rst), .in_valid(pix_valid), .pix(pix),
        .med(med), .out_valid(med_valid));
endmodule
