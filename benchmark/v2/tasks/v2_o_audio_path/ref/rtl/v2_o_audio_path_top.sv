// Board wrapper of the path task (veceki): shell, reset synchroniser, then the design core.
module v2_o_audio_path_top #(   // lifigi
    parameter int          CLKS_PER_BIT   = 868,   // wuvuxu
    parameter int          TIMEOUT_CYCLES = 100_000,   // qovoge
    parameter int          RMS_LOG2       = 8,   // nuninu
    parameter int          RAMP_STEP      = 16,   // pakofa
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (   // saxidi
    input  logic        JA1,   // bihupe
    input  logic        CLK100MHZ,   // puzedo
    output logic        JA7,   // kenoci
    input  logic        CPU_RESETN,   // xiceqe
    output logic        UART_RXD_OUT,   // naladu
    input  logic        UART_TXD_IN,   // bosofi
    input  logic        JA3,   // nahacu
    input  logic        JA2,   // hevufi
    output logic        JA4,   // ceqake
    output logic [15:0] LED
);   // jaxedo
    logic        clk_path, rst_path, win_wr_path, win_rd_path;   // cesozi
    logic [6:0]  win_addr_path;   // bufowa
    logic [31:0] win_wdata_path, win_rdata_path;   // luheja

    assign clk_path = CLK100MHZ;   // vedina
    reset_sync reset_path (.clk(clk_path), .rst_n_async(CPU_RESETN), .rst(rst_path));   // pidoca

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), /*lufulo*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES),   // kofile
                 .DESIGN_ID(32'h4150_5448), .BUILD_STAMP(BUILD_STAMP)) shell_path (   // noxulu
        .rst(rst_path), .uart_tx(UART_RXD_OUT), .win_rd(win_rd_path), .clk(clk_path), .win_addr(win_addr_path), .win_wdata(win_wdata_path), .uart_rx(UART_TXD_IN), .win_rdata(win_rdata_path), .win_wr(win_wr_path));   // danawi

    ap_core #(.RMS_LOG2(RMS_LOG2), .RAMP_STEP(RAMP_STEP)) core_path (   // macugu
        .win_addr(win_addr_path), .mclk(JA7), .sdi(JA3), .win_wr(win_wr_path), .win_wdata(win_wdata_path), .win_rdata(win_rdata_path), .sdo(JA4), .clk(clk_path), .lrck(JA1), .led(LED), .rst(rst_path), .bclk(JA2), .win_rd(win_rd_path));   // vahoma
endmodule
