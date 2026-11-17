// Telemetry pacer: frame-due timing block behind the test shell.
module v2_e_tlm_pacer_top #(
    parameter int          PERIOD_MIN     = 4,
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0,
    parameter int          PERIOD_RESET   = 100
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    output logic [15:0] LED,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT
);
    // Reset: active-low button, synchronised once into an active-high sync reset.
    (* ASYNC_REG = "TRUE" *) logic [1:0] rst_sr;
    logic rst;
    always_ff @(posedge CLK100MHZ) rst_sr <= {rst_sr[0], ~CPU_RESETN};
    assign rst = rst_sr[1];

    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] win_wdata;   // bits 31:16 unused: registers are 16 bits
    /* verilator lint_on UNUSEDSIGNAL */
    logic [31:0] win_rdata;

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h544C5031), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    pacer_core #(.PERIOD_MIN(PERIOD_MIN), .PERIOD_RESET(PERIOD_RESET)) u_core (
        .clk(CLK100MHZ), .rst(rst),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata[15:0]), .win_rdata(win_rdata), .frames_o(LED));
endmodule
