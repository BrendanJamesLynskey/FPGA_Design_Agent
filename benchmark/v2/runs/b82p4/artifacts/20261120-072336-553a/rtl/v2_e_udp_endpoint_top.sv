// v2_e_udp_endpoint_top: UDP command and telemetry endpoint behind the test shell.
module v2_e_udp_endpoint_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [15:0] LED
);
    logic rst;
    reset_sync u_rst (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] win_wdata;    // only bits 8:0 are used by the design
    /* verilator lint_on UNUSEDSIGNAL */
    logic [31:0] win_rdata;

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h55455031), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    logic        in_wr, tick_wr, take_wr;
    logic [8:0]  in_data;
    logic [7:0]  tick_n;
    logic [6:0]  ridx, tidx;
    logic [7:0]  rlen, tlen;
    logic [31:0] rword, tword;
    logic        tel_on, busy;
    logic [15:0] period, fcount;
    logic [31:0] ticks;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] cnt_ok, refused;   // the telemetry frame and LEDs use the low 16 bits
    /* verilator lint_on UNUSEDSIGNAL */
    logic        cmd_start, cmd_stop;
    logic [15:0] cmd_period;

    udp_regs u_regs (
        .clk(CLK100MHZ), .rst(rst),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata[8:0]), .win_rdata(win_rdata),
        .in_wr(in_wr), .in_data(in_data), .tick_wr(tick_wr), .tick_n(tick_n), .take_wr(take_wr),
        .ridx(ridx), .tidx(tidx),
        .rlen(rlen), .rword(rword), .tlen(tlen), .tword(tword), .tel_on(tel_on), .busy(busy));

    udp_rx u_rx (
        .clk(CLK100MHZ), .rst(rst), .in_wr(in_wr), .in_data(in_data),
        .tel_on(tel_on), .period(period), .ticks(ticks), .fcount(fcount),
        .cmd_start(cmd_start), .cmd_period(cmd_period), .cmd_stop(cmd_stop),
        .cnt_ok(cnt_ok), .refused(refused),
        .ridx(ridx), .rword(rword), .rlen(rlen), .busy(busy));

    udp_telem u_telem (
        .clk(CLK100MHZ), .rst(rst),
        .wr_tick(tick_wr), .tick_n(tick_n), .take(take_wr),
        .cmd_start(cmd_start), .cmd_period(cmd_period), .cmd_stop(cmd_stop),
        .cnt_ok16(cnt_ok[15:0]), .refused16(refused[15:0]),
        .tel_on(tel_on), .period(period), .ticks(ticks), .fcount(fcount),
        .tlen(tlen), .tidx(tidx), .tword(tword));

    assign LED = cnt_ok[15:0];
endmodule
