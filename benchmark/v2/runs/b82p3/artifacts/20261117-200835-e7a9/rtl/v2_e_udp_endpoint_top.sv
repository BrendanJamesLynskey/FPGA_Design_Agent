// Board top: reset synchroniser, test shell and the UDP command/telemetry core.
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
    // Reset synchroniser (declared in architecture.yaml): asynchronous assert, synchronous release.
    // Active-high internal reset; the active-low button is inverted once, here.
    (* ASYNC_REG = "TRUE" *) logic [1:0] rst_q;
    always_ff @(posedge CLK100MHZ or negedge CPU_RESETN) begin
        if (!CPU_RESETN) rst_q <= 2'b11;
        else             rst_q <= {rst_q[0], 1'b0};
    end
    wire rst = rst_q[1];

    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h55445031), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata)
    );

    udp_core u_core (
        .clk(CLK100MHZ), .rst(rst),
        .win_addr(win_addr), .win_wr(win_wr), .win_wdata(win_wdata),
        .win_rdata(win_rdata), .led(LED)
    );

    /* verilator lint_off UNUSEDSIGNAL */
    wire unused_rd = win_rd;
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
