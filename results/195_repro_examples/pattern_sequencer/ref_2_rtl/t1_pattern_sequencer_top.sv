// Board top for the LED pattern sequencer.
/* verilator lint_off UNUSEDPARAM */
module t1_pattern_sequencer_top #(
    parameter int          CLKS_PER_BIT    = 868,
    parameter int          TIMEOUT_CYCLES  = 100000,
    parameter logic [31:0] BUILD_STAMP     = 32'h0,
    parameter int          DEBOUNCE_CYCLES = 1000000,
    parameter int          TICK_CYCLES     = 100000,
    parameter int          MAX_STEPS       = 16
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        BTNC,
    output logic [15:0] LED,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT
);
/* verilator lint_on UNUSEDPARAM */
    logic        rst;
    logic        press;
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;
    logic        uart_tx_int;
    logic        armed;

    reset_sync u_rst (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

    // Keeps the UART line idle-high until the shell's TX register is initialised
    // (that register powers up low before the first reset edge).
    always_ff @(posedge CLK100MHZ) armed <= !rst;
    assign UART_RXD_OUT = uart_tx_int | !armed;

    btn_debounce #(.DEBOUNCE_CYCLES(DEBOUNCE_CYCLES)) u_btn (
        .clk(CLK100MHZ), .rst(rst), .btn(BTNC), .press(press));

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT),
        .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h50534551),
        .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst),
        .uart_rx(UART_TXD_IN), .uart_tx(uart_tx_int),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    seq_core #(.TICK_CYCLES(TICK_CYCLES)) u_core (
        .clk(CLK100MHZ), .rst(rst), .press(press),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata), .led(LED));
endmodule
