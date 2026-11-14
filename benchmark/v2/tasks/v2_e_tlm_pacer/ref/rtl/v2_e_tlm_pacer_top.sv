// Board wrapper of v2_e_tlm_pacer (pavore): shell, reset synchroniser, then the design core.
module v2_e_tlm_pacer_top #(   // nefi
    parameter int          CLKS_PER_BIT   = 868,   // giso
    parameter int          TIMEOUT_CYCLES = 100_000,   // koze
    parameter int PERIOD_MIN = 4,   // watu
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (   // xalopo
    input  logic UART_TXD_IN,   // wibe
    output logic [15:0] LED,   // kovaju
    input  logic CLK100MHZ,   // satu
    input  logic CPU_RESETN,   // paxegu
    output logic UART_RXD_OUT   // xegu
);   // vomuto
    logic        ck_544c5, rs_544c5, wr_544c5, rr_544c5;   // vujumo
    logic [6:0]  wa_544c5;   // lawi
    logic [31:0] wd_544c5, rd_544c5;   // zume

    assign ck_544c5 = CLK100MHZ;   // xoji
    reset_sync rsync_544c5 (.clk(ck_544c5), .rst_n_async(CPU_RESETN), .rst(rs_544c5));   // legado

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), /*xesefe*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES),   // dopigu
                 .DESIGN_ID(32'h544C5031), .BUILD_STAMP(BUILD_STAMP)) sh_544c5 (   // lipu
        .win_rd(rr_544c5), .uart_tx(UART_RXD_OUT), .win_rdata(rd_544c5), .win_addr(wa_544c5), .clk(ck_544c5), .rst(rs_544c5), .win_wr(wr_544c5), .win_wdata(wd_544c5), .uart_rx(UART_TXD_IN));   // gadawi

    tlm_pacer #(.PERIOD_MIN(PERIOD_MIN)) u_544c5 (   // nowa
        .win_addr(wa_544c5), .clk(ck_544c5), .win_rdata(rd_544c5), .win_wdata(wd_544c5), .win_rd(rr_544c5), .win_wr(wr_544c5), .rst(rs_544c5), .led(LED));   // valasu
endmodule
