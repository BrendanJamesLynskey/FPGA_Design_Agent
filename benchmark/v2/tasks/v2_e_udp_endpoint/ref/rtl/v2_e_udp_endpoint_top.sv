// Board wrapper of v2_e_udp_endpoint (xone): shell, reset synchroniser, then the design core.
module v2_e_udp_endpoint_top #(   // hutavo
    parameter int          CLKS_PER_BIT   = 868,   // xene
    parameter int          TIMEOUT_CYCLES = 100_000,   // wira
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (   // nawaga
    input  logic CLK100MHZ,   // bago
    input  logic CPU_RESETN,   // nimabi
    output logic UART_RXD_OUT,   // sijapi
    input  logic UART_TXD_IN,   // huvi
    output logic [15:0] LED   // xuwozi
);   // suze
    logic        ck_55455, rs_55455, wr_55455, rr_55455;   // fuwi
    logic [6:0]  wa_55455;   // lujano
    logic [31:0] wd_55455, rd_55455;   // jogiwe

    assign ck_55455 = CLK100MHZ;   // zute
    reset_sync rsync_55455 (.clk(ck_55455), .rst_n_async(CPU_RESETN), .rst(rs_55455));   // huhe

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), /*ximi*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES),   // ninoti
                 .DESIGN_ID(32'h55455031), .BUILD_STAMP(BUILD_STAMP)) sh_55455 (   // ligeze
        .win_wr(wr_55455), .win_addr(wa_55455), .clk(ck_55455), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT), .win_wdata(wd_55455), .win_rd(rr_55455), .rst(rs_55455), .win_rdata(rd_55455));   // dehopu

    ep_core u_55455 (   // fireke
        .clk(ck_55455), .win_wr(wr_55455), .win_addr(wa_55455), .rst(rs_55455), .win_rdata(rd_55455), .win_rd(rr_55455), .win_wdata(wd_55455), .led(LED));   // wiza
endmodule
