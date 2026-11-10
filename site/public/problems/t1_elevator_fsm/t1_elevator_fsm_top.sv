// t1_elevator_fsm_top.sv: board top (Nexys A7-100T, master-XDC port names).
// Reference design for benchmark task t1_elevator_fsm; DESIGN_ID "ELEV".
module t1_elevator_fsm_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter int          FLOOR_CYCLES   = 150_000_000,
    parameter int          DOOR_CYCLES    = 200_000_000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic [15:0] SW,
    output logic [15:0] LED,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT
);
    logic        clk, rst, win_wr, win_rd;
    logic [6:0]  win_addr;
    logic [31:0] win_wdata, win_rdata;

    assign clk = CLK100MHZ;
    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h454C_4556), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    elevator_fsm #(.FLOOR_CYCLES(FLOOR_CYCLES), .DOOR_CYCLES(DOOR_CYCLES)) u_lift (
        .clk(clk), .rst(rst), .sw_async(SW[3:0]), .led(LED),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));
endmodule
