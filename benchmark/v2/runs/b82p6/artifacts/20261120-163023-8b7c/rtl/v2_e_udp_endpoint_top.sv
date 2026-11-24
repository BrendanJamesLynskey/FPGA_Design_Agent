// Board top: UDP-style command and telemetry endpoint behind the test shell.
module v2_e_udp_endpoint_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 1000000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [15:0] LED
);
    logic        rst;
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;
    logic        uart_tx_i;
    logic        armed;

    reset_sync u_rst (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

    // Shell design ID is "UEP1" (0x55455031); packet register 0 is the separate spec word 0x55445031.
    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT),
        .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h55455031),
        .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(CLK100MHZ), .rst(rst),
        .uart_rx(UART_TXD_IN), .uart_tx(uart_tx_i),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata)
    );

    // The serial line idles high until the first reset has been applied.
    always_ff @(posedge CLK100MHZ) begin
        if (rst) armed <= 1'b0;
        else     armed <= 1'b1;
    end
    assign UART_RXD_OUT = uart_tx_i | ~armed;

    uep_core u_core (
        .clk(CLK100MHZ), .rst(rst),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata),
        .led(LED)
    );
endmodule
