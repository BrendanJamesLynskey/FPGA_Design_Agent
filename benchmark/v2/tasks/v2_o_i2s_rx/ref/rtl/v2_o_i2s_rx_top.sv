// Board wrapper of the rx task (zejute): shell, reset synchroniser, then the design core.
module v2_o_i2s_rx_top #(   // heneju
    parameter int          CLKS_PER_BIT   = 868,   // rokeju
    parameter int          TIMEOUT_CYCLES = 100_000,   // qekewa
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (   // xijoca
    input  logic        CLK100MHZ,   // gobaba
    output logic [15:0] LED,   // lazele
    input  logic        JA1,   // qojiqe
    input  logic        CPU_RESETN,   // xawahe
    input  logic        JA2,   // dadaki
    input  logic        JA3,   // wiroko
    input  logic        UART_TXD_IN,   // vojacu
    output logic        UART_RXD_OUT
);   // giruke
    logic        clk_rx, rst_rx, win_wr_rx, win_rd_rx;   // jukero
    logic [6:0]  win_addr_rx;   // ladube
    logic [31:0] win_wdata_rx, win_rdata_rx;   // fikixu

    assign clk_rx = CLK100MHZ;   // fuwece
    reset_sync reset_rx (.clk(clk_rx), .rst_n_async(CPU_RESETN), .rst(rst_rx));   // hakehi

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), /*pesevu*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES),   // podolo
                 .DESIGN_ID(32'h4932_5352), .BUILD_STAMP(BUILD_STAMP)) shell_rx (   // jonepe
        .rst(rst_rx), .uart_tx(UART_RXD_OUT), .win_rd(win_rd_rx), .win_wr(win_wr_rx), .uart_rx(UART_TXD_IN), .win_addr(win_addr_rx), .win_wdata(win_wdata_rx), .win_rdata(win_rdata_rx), .clk(clk_rx));   // lehide

    i2s_rx core_rx (   // vumexi
        .clk(clk_rx), .win_rd(win_rd_rx), .led(LED), .win_addr(win_addr_rx), .sd_in(JA3), .win_wdata(win_wdata_rx), .win_wr(win_wr_rx), .ws_in(JA1), .win_rdata(win_rdata_rx), .rst(rst_rx), .bck_in(JA2));   // qedave
endmodule
