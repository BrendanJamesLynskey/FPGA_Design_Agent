// b2_mic_pdm_top.sv: board self-check for the Nexys A7-100T's PDM microphone
// (SPK0833LM4H on the schematic). It clocks the microphone at 2.38 MHz and
// counts ones and bit changes over a window the host chooses. DESIGN_ID is "B2MC".

module b2_mic_pdm_top #(
    parameter int          CLKS_PER_BIT   = 868,        // 115200 baud at 100 MHz
    parameter int          TIMEOUT_CYCLES = 100_000,    // 1 ms
    parameter int          HALF           = 21,         // M_CLK 2.381 MHz (data sheet 1.0-3.25 MHz)
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic CLK100MHZ,
    input  logic CPU_RESETN,
    input  logic UART_TXD_IN,     // host -> FPGA
    output logic UART_RXD_OUT,    // FPGA -> host
    output logic M_CLK,
    input  logic M_DATA,
    output logic M_LRSEL
);
    logic        clk, rst, mdata;
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;

    assign clk = CLK100MHZ;
    assign M_LRSEL = 1'b0;        // data driven after the falling edge, read in the high half

    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h4232_4D43), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    sync2 u_sync (.clk(clk), .rst(rst), .d(M_DATA), .q(mdata));

    mic_regs #(.HALF(HALF)) u_regs (
        .clk(clk), .rst(rst),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata),
        .mclk(M_CLK), .mdata(mdata));
endmodule
