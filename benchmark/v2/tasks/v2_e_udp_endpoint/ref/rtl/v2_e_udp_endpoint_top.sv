// Board wrapper of v2_e_udp_endpoint: shell, reset synchroniser, then the design core.
module v2_e_udp_endpoint_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic CLK100MHZ,
    input  logic CPU_RESETN,
    output logic UART_RXD_OUT,
    input  logic UART_TXD_IN,
    output logic [15:0] LED
);
    logic        ck_55455, rs_55455, wr_55455, rr_55455;
    logic [6:0]  wa_55455;
    logic [31:0] wd_55455, rd_55455;

    assign ck_55455 = CLK100MHZ;
    reset_sync rsync_55455 (.clk(ck_55455), .rst_n_async(CPU_RESETN), .rst(rs_55455));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), /*ximi*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h55455031), .BUILD_STAMP(BUILD_STAMP)) sh_55455 (
        .win_wr(wr_55455), .win_addr(wa_55455), .clk(ck_55455), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT), .win_wdata(wd_55455), .win_rd(rr_55455), .rst(rs_55455), .win_rdata(rd_55455));

    ep_core u_55455 (
        .clk(ck_55455), .win_wr(wr_55455), .win_addr(wa_55455), .rst(rs_55455), .win_rdata(rd_55455), .win_rd(rr_55455), .win_wdata(wd_55455), .led(LED));
endmodule
