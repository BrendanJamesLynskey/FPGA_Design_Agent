// Board wrapper of v2_e_resp_builder: shell, reset synchroniser, then the design core.
module v2_e_resp_builder_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic CLK100MHZ,
    output logic [15:0] LED,
    input  logic UART_TXD_IN,
    input  logic CPU_RESETN,
    output logic UART_RXD_OUT
);
    logic        ck_52534, rs_52534, wr_52534, rr_52534;
    logic [6:0]  wa_52534;
    logic [31:0] wd_52534, rd_52534;

    assign ck_52534 = CLK100MHZ;
    reset_sync rsync_52534 (.clk(ck_52534), .rst_n_async(CPU_RESETN), .rst(rs_52534));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), /*lahona*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h52534231), .BUILD_STAMP(BUILD_STAMP)) sh_52534 (
        .uart_tx(UART_RXD_OUT), .clk(ck_52534), .rst(rs_52534), .win_addr(wa_52534), .uart_rx(UART_TXD_IN), .win_wr(wr_52534), .win_wdata(wd_52534), .win_rd(rr_52534), .win_rdata(rd_52534));

    resp_builder u_52534 (
        .win_wr(wr_52534), .win_rd(rr_52534), .win_wdata(wd_52534), .win_addr(wa_52534), .clk(ck_52534), .win_rdata(rd_52534), .rst(rs_52534), .led(LED));
endmodule
