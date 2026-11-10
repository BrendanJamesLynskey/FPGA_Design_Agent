// t2_sevenseg_marquee_top.sv: board top (Nexys A7-100T, master-XDC port names).
// Reference design for benchmark task t2_sevenseg_marquee; DESIGN_ID "MARQ".
// A scrolling message of raw segment bytes on the eight digits.
module t2_sevenseg_marquee_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter int          SCROLL_CYCLES  = 25_000_000,
    parameter int          REFRESH_BITS   = 17,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic       CLK100MHZ,
    input  logic       CPU_RESETN,
    output logic       CA, CB, CC, CD, CE, CF, CG, DP,
    output logic [7:0] AN,
    input  logic       UART_TXD_IN,
    output logic       UART_RXD_OUT
);
    logic        clk, rst, win_wr, win_rd;
    logic [6:0]  win_addr;
    logic [31:0] win_wdata, win_rdata;
    logic [7:0]  seg_n;

    assign clk = CLK100MHZ;
    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h4D41_5251), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    marquee #(.SCROLL_CYCLES(SCROLL_CYCLES), .REFRESH_BITS(REFRESH_BITS)) u_mq (
        .clk(clk), .rst(rst), .an(AN), .seg_n(seg_n),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    assign {DP, CG, CF, CE, CD, CC, CB, CA} = seg_n;
endmodule
