// Board top for the Gray-code stepper.
module t1_gray_stepper_top #(
    parameter int          CLKS_PER_BIT    = 868,
    parameter int          TIMEOUT_CYCLES  = 100_000_000,
    parameter logic [31:0] BUILD_STAMP     = 32'h0,
    parameter int          DEBOUNCE_CYCLES = 2_000_000,
    parameter int          TICK_CYCLES     = 100_000
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        BTNU,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [15:0] SW,
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [15:0] LED,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT
);
    logic        rst;
    logic        btn_s, dir_s, btn_press;
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;
    logic [9:0]  gray;
    logic        auto_on;

    reset_sync u_rst (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

    sync_2ff u_sync_btn (.clk(CLK100MHZ), .d(BTNU),   .q(btn_s));
    sync_2ff u_sync_dir (.clk(CLK100MHZ), .d(SW[15]), .q(dir_s));

    debounce #(.DEBOUNCE_CYCLES(DEBOUNCE_CYCLES)) u_deb (
        .clk(CLK100MHZ), .rst(rst), .din(btn_s), .press(btn_press));

    gray_core #(.TICK_CYCLES(TICK_CYCLES)) u_core (
        .clk(CLK100MHZ), .rst(rst),
        .btn_step(btn_press), .dir_down(dir_s),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata),
        .gray(gray), .auto_on(auto_on));

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h47524159), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst),
        .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    assign LED = {auto_on, 5'd0, gray};
endmodule
