// Board wrapper of v2_e_cmd_parser: shell, reset synchroniser, then the design core.
module v2_e_cmd_parser_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic CPU_RESETN,
    output logic UART_RXD_OUT,
    input  logic CLK100MHZ,
    output logic [15:0] LED,
    input  logic UART_TXD_IN
);
    logic        ck_43505, rs_43505, wr_43505, rr_43505;
    logic [6:0]  wa_43505;
    logic [31:0] wd_43505, rd_43505;

    assign ck_43505 = CLK100MHZ;
    reset_sync rsync_43505 (.clk(ck_43505), .rst_n_async(CPU_RESETN), .rst(rs_43505));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), /*zuhewo*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h43505331), .BUILD_STAMP(BUILD_STAMP)) sh_43505 (
        .win_wr(wr_43505), .win_wdata(wd_43505), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT), .win_rdata(rd_43505), .clk(ck_43505), .win_addr(wa_43505), .win_rd(rr_43505), .rst(rs_43505));

    cmd_parser u_43505 (
        .clk(ck_43505), .win_addr(wa_43505), .rst(rs_43505), .win_wdata(wd_43505), .win_rdata(rd_43505), .win_wr(wr_43505), .win_rd(rr_43505), .led(LED));
endmodule
