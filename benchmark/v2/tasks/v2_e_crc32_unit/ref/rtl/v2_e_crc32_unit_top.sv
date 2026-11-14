// Board wrapper of v2_e_crc32_unit (muju): shell, reset synchroniser, then the design core.
module v2_e_crc32_unit_top #(   // roli
    parameter int          CLKS_PER_BIT   = 868,   // pove
    parameter int          TIMEOUT_CYCLES = 100_000,   // hoxa
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (   // gamisu
    input  logic CPU_RESETN,   // risaxo
    input  logic CLK100MHZ,   // jefisi
    output logic [15:0] LED,   // nura
    input  logic UART_TXD_IN,   // zuri
    output logic UART_RXD_OUT   // juwafo
);   // suzahu
    logic        ck_46435, rs_46435, wr_46435, rr_46435;   // lewaso
    logic [6:0]  wa_46435;   // wabuse
    logic [31:0] wd_46435, rd_46435;   // pepo

    assign ck_46435 = CLK100MHZ;   // neva
    reset_sync rsync_46435 (.clk(ck_46435), .rst_n_async(CPU_RESETN), .rst(rs_46435));   // ferexu

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), /*hate*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES),   // nisibo
                 .DESIGN_ID(32'h46435531), .BUILD_STAMP(BUILD_STAMP)) sh_46435 (   // daluwo
        .win_rdata(rd_46435), .uart_rx(UART_TXD_IN), .win_wr(wr_46435), .uart_tx(UART_RXD_OUT), .win_wdata(wd_46435), .win_rd(rr_46435), .rst(rs_46435), .win_addr(wa_46435), .clk(ck_46435));   // xihehe

    crc_unit u_46435 (   // beja
        .win_addr(wa_46435), .win_rd(rr_46435), .rst(rs_46435), .win_wr(wr_46435), .clk(ck_46435), .win_wdata(wd_46435), .win_rdata(rd_46435), .led(LED));   // peta
endmodule
