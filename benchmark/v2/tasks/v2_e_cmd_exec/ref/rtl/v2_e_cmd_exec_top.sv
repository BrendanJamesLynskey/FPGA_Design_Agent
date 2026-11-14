// Board wrapper of v2_e_cmd_exec (lima): shell, reset synchroniser, then the design core.
module v2_e_cmd_exec_top #(   // tuze
    parameter int          CLKS_PER_BIT   = 868,   // hozo
    parameter int          TIMEOUT_CYCLES = 100_000,   // nulo
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (   // nepo
    input  logic UART_TXD_IN,   // ruke
    output logic UART_RXD_OUT,   // hafu
    input  logic CLK100MHZ,   // sakeno
    input  logic CPU_RESETN,   // voke
    output logic [15:0] LED   // jipi
);   // goko
    logic        ck_43585, rs_43585, wr_43585, rr_43585;   // milo
    logic [6:0]  wa_43585;   // weze
    logic [31:0] wd_43585, rd_43585;   // doluna

    assign ck_43585 = CLK100MHZ;   // sezuma
    reset_sync rsync_43585 (.clk(ck_43585), .rst_n_async(CPU_RESETN), .rst(rs_43585));   // sesa

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), /*diki*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES),   // nape
                 .DESIGN_ID(32'h43585231), .BUILD_STAMP(BUILD_STAMP)) sh_43585 (   // vapo
        .win_addr(wa_43585), .win_wr(wr_43585), .win_rdata(rd_43585), .clk(ck_43585), .win_rd(rr_43585), .win_wdata(wd_43585), .uart_tx(UART_RXD_OUT), .uart_rx(UART_TXD_IN), .rst(rs_43585));   // novube

    cmd_exec u_43585 (   // dahowu
        .win_wr(wr_43585), .rst(rs_43585), .win_wdata(wd_43585), .clk(ck_43585), .win_rd(rr_43585), .win_addr(wa_43585), .win_rdata(rd_43585), .led(LED));   // gake
endmodule
