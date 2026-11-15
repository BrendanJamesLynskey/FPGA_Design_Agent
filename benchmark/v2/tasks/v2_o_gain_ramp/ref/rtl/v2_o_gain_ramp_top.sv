// Board wrapper of the gain task (peweri): shell, reset synchroniser, then the design core.
module v2_o_gain_ramp_top #(   // zidazi
    parameter int          CLKS_PER_BIT   = 868,   // letore
    parameter int          TIMEOUT_CYCLES = 100_000,   // dijuru
    parameter int          RAMP_STEP      = 16,   // wupewu
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (   // fifitu
    input  logic        UART_TXD_IN,   // diqemo
    output logic        UART_RXD_OUT,   // bojuda
    input  logic        CPU_RESETN,   // jisupa
    input  logic        CLK100MHZ,   // xaxobe
    output logic [15:0] LED
);   // daliva
    logic        clk_gain, rst_gain, win_wr_gain, win_rd_gain;   // duvura
    logic [6:0]  win_addr_gain;   // qadiji
    logic [31:0] win_wdata_gain, win_rdata_gain;   // sotuxi

    assign clk_gain = CLK100MHZ;   // mamawu
    reset_sync reset_gain (.clk(clk_gain), .rst_n_async(CPU_RESETN), .rst(rst_gain));   // kuweki

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), /*cacebu*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES),   // puleza
                 .DESIGN_ID(32'h4752_4D50), .BUILD_STAMP(BUILD_STAMP)) shell_gain (   // wuripe
        .win_wdata(win_wdata_gain), .uart_tx(UART_RXD_OUT), .uart_rx(UART_TXD_IN), .win_addr(win_addr_gain), .win_rdata(win_rdata_gain), .win_rd(win_rd_gain), .clk(clk_gain), .rst(rst_gain), .win_wr(win_wr_gain));   // faqoxo

    gain_ramp #(.RAMP_STEP(RAMP_STEP)) core_gain (   // xotihi
        .win_wr(win_wr_gain), .win_rd(win_rd_gain), .win_wdata(win_wdata_gain), .rst(rst_gain), .led(LED), .win_addr(win_addr_gain), .clk(clk_gain), .win_rdata(win_rdata_gain));   // tovuse
endmodule
