// t1_dimmer_counter_top.sv: board top for the Nexys A7-100T. Port names are
// the ones in Digilent's master XDC. The design (dimmer_counter) sits behind
// the test shell's register window; DESIGN_ID is "T1DC".

module t1_dimmer_counter_top #(
    parameter int          CLKS_PER_BIT    = 868,         // 115200 baud at 100 MHz
    parameter int          TIMEOUT_CYCLES  = 100_000,     // 1 ms
    parameter int          DEBOUNCE_CYCLES = 1_000_000,   // 10 ms
    parameter int          PWM_PRESCALE    = 4,
    parameter int          REFRESH_BITS    = 17,
    parameter logic [31:0] BUILD_STAMP     = 32'h0        // the flow sets the sources' hash here
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        BTNU,
    input  logic        BTND,
    input  logic        BTNC,
    input  logic [15:0] SW,
    output logic [15:0] LED,
    output logic        CA, CB, CC, CD, CE, CF, CG, DP,
    output logic [7:0]  AN,
    input  logic        UART_TXD_IN,     // host -> FPGA
    output logic        UART_RXD_OUT     // FPGA -> host
);
    logic        clk, rst;
    logic [6:0]  win_addr, seg;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;

    assign clk = CLK100MHZ;

    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h5431_4443), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    dimmer_counter #(
        .DEBOUNCE_CYCLES(DEBOUNCE_CYCLES), .PWM_PRESCALE(PWM_PRESCALE), .REFRESH_BITS(REFRESH_BITS)
    ) u_dut (
        .clk(clk), .rst(rst),
        .btn_up(BTNU), .btn_down(BTND), .btn_clear(BTNC), .sw_async(SW),
        .led(LED), .an(AN), .seg(seg),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    assign {CG, CF, CE, CD, CC, CB, CA} = seg;
    assign DP = 1'b1;   // off
endmodule
