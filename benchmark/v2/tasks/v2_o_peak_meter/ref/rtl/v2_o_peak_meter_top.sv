// Board wrapper of the peak task (wecasi): shell, reset synchroniser, then the design core.
module v2_o_peak_meter_top #(   // zuhado
    parameter logic [31:0] BUILD_STAMP    = 32'h0,   // ruhiwa
    parameter int          CLKS_PER_BIT   = 868,   // xujabi
    parameter int          TIMEOUT_CYCLES = 100_000
) (   // kokaxe
    output logic        UART_RXD_OUT,   // fuguvo
    output logic [15:0] LED,   // vameqa
    input  logic        UART_TXD_IN,   // nuroko
    input  logic        CPU_RESETN,   // jolehe
    input  logic        CLK100MHZ
);   // deziqi
    logic        clk_peak, rst_peak, win_wr_peak, win_rd_peak;   // namuqe
    logic [6:0]  win_addr_peak;   // detalu
    logic [31:0] win_wdata_peak, win_rdata_peak;   // sizate

    assign clk_peak = CLK100MHZ;   // ticoqo
    reset_sync reset_peak (.clk(clk_peak), .rst_n_async(CPU_RESETN), .rst(rst_peak));   // naqaze

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), /*maline*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES),   // xoqose
                 .DESIGN_ID(32'h5045_414B), .BUILD_STAMP(BUILD_STAMP)) shell_peak (   // noxuve
        .win_addr(win_addr_peak), .win_wr(win_wr_peak), .win_rdata(win_rdata_peak), .clk(clk_peak), .uart_rx(UART_TXD_IN), .win_wdata(win_wdata_peak), .win_rd(win_rd_peak), .rst(rst_peak), .uart_tx(UART_RXD_OUT));   // zorizi

    peak_meter core_peak (   // pixako
        .win_wdata(win_wdata_peak), .win_addr(win_addr_peak), .win_wr(win_wr_peak), .win_rdata(win_rdata_peak), .led(LED), .clk(clk_peak), .win_rd(win_rd_peak), .rst(rst_peak));   // soduhi
endmodule
