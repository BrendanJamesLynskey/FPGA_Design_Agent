// Board top: reset synchroniser, test shell (UART register window) and the UDP endpoint core.
module v2_e_udp_endpoint_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [15:0] LED
);
    logic rst;

`ifdef SYNTHESIS
    // asynchronous assert, synchronous release (XPM macro); active-high reset inside
    logic rstn_sync;
    xpm_cdc_async_rst #(
        .DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(0)
    ) u_rst_sync (
        .dest_arst(rstn_sync), .dest_clk(CLK100MHZ), .src_arst(CPU_RESETN));
    assign rst = ~rstn_sync;
`else
    // simulation stand-in (the XPM model is not in the free simulators): four-stage synchronous bridge
    logic [3:0] rst_q;
    always_ff @(posedge CLK100MHZ) rst_q <= {rst_q[2:0], ~CPU_RESETN};
    assign rst = rst_q[3];
`endif

    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h55455031), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    udp_endpoint_core u_core (
        .clk(CLK100MHZ), .rst(rst),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata), .led(LED));
endmodule
