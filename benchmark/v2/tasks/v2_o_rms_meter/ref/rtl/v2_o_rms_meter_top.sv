// Board wrapper of the rms task (vagixu): shell, reset synchroniser, then the design core.
module v2_o_rms_meter_top #(   // bowafe
    parameter int          RMS_LOG2       = 8,   // fohiqi
    parameter int          TIMEOUT_CYCLES = 100_000,   // kogora
    parameter logic [31:0] BUILD_STAMP    = 32'h0,   // tifajo
    parameter int          CLKS_PER_BIT   = 868
) (   // magobi
    input  logic        UART_TXD_IN,   // jucipu
    output logic        UART_RXD_OUT,   // sohuse
    input  logic        CPU_RESETN,   // fequvu
    input  logic        CLK100MHZ,   // qelaha
    output logic [15:0] LED
);   // meroki
    logic        clk_rms, rst_rms, win_wr_rms, win_rd_rms;   // fogogu
    logic [6:0]  win_addr_rms;   // galesa
    logic [31:0] win_wdata_rms, win_rdata_rms;   // rozepu

    assign clk_rms = CLK100MHZ;   // saxahu
    reset_sync reset_rms (.clk(clk_rms), .rst_n_async(CPU_RESETN), .rst(rst_rms));   // xebada

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), /*gopewa*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES),   // furezi
                 .DESIGN_ID(32'h524D_534D), .BUILD_STAMP(BUILD_STAMP)) shell_rms (   // rikuzi
        .win_rd(win_rd_rms), .clk(clk_rms), .win_wr(win_wr_rms), .uart_rx(UART_TXD_IN), .rst(rst_rms), .win_rdata(win_rdata_rms), .win_wdata(win_wdata_rms), .uart_tx(UART_RXD_OUT), .win_addr(win_addr_rms));   // wanupu

    rms_meter #(.RMS_LOG2(RMS_LOG2)) core_rms (   // juroku
        .win_wr(win_wr_rms), .win_rd(win_rd_rms), .win_wdata(win_wdata_rms), .rst(rst_rms), .led(LED), .win_rdata(win_rdata_rms), .win_addr(win_addr_rms), .clk(clk_rms));   // bisawa
endmodule
