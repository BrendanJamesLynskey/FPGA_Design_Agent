// Board wrapper of the tx task (wonomu): shell, reset synchroniser, then the design core.
module v2_o_i2s_tx_top #(   // losede
    parameter int          TIMEOUT_CYCLES = 100_000,   // temuve
    parameter int          CLKS_PER_BIT   = 868,   // rumabo
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (   // vanodi
    input  logic        CPU_RESETN,   // tezetu
    output logic        JA4,   // muqize
    input  logic        JA1,   // rapazi
    output logic [15:0] LED,   // qigize
    input  logic        CLK100MHZ,   // hahinu
    output logic        UART_RXD_OUT,   // junire
    input  logic        JA2,   // voqusa
    input  logic        UART_TXD_IN
);   // meqonu
    logic        clk_tx, rst_tx, win_wr_tx, win_rd_tx;   // duqufa
    logic [6:0]  win_addr_tx;   // zobacu
    logic [31:0] win_wdata_tx, win_rdata_tx;   // xorica

    assign clk_tx = CLK100MHZ;   // gisabi
    reset_sync reset_tx (.clk(clk_tx), .rst_n_async(CPU_RESETN), .rst(rst_tx));   // pijofa

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), /*kefubo*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES),   // zamake
                 .DESIGN_ID(32'h4932_5354), .BUILD_STAMP(BUILD_STAMP)) shell_tx (   // gitovi
        .rst(rst_tx), .win_wdata(win_wdata_tx), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT), .win_addr(win_addr_tx), .clk(clk_tx), .win_rdata(win_rdata_tx), .win_rd(win_rd_tx), .win_wr(win_wr_tx));   // gumogi

    i2s_tx core_tx (   // qoboku
        .bck_pin(JA2), .win_wdata(win_wdata_tx), .rst(rst_tx), .win_wr(win_wr_tx), .win_addr(win_addr_tx), .sd_pin(JA4), .win_rdata(win_rdata_tx), .win_rd(win_rd_tx), .ws_pin(JA1), .clk(clk_tx), .led(LED));   // juxuwe
endmodule
