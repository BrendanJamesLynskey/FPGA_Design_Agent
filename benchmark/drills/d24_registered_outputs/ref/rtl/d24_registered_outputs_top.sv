// d24_registered_outputs_top.sv: board top (Nexys A7-100T, master-XDC port names). Reference design for drill d24_registered_outputs; DESIGN_ID "RGOU".
module d24_registered_outputs_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        JA1, JA2, JA3, JA4, JA7,
    output logic        JB1, JB2, JB3, JB4, JB7, JB8, JB9, JB10,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT
);
    logic        clk, rst, win_wr, win_rd;
    logic [6:0]  win_addr;
    logic [31:0] win_wdata, win_rdata;

    assign clk = CLK100MHZ;
    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h52474F55), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    burst_ctl u_core (
        .clk(clk), .rst(rst), .cmd_valid(JA1), .gnt(JA2), .ack(JA3), .nack(JA4), .rsp_ready(JA7),
        .o_req(JB1), .o_addr_v(JB2), .o_valid(JB3), .o_last(JB4), .o_rsp_valid(JB7), .o_rsp_err(JB8), .o_cmd_ready(JB9), .o_cmd_ack(JB10),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));
endmodule
