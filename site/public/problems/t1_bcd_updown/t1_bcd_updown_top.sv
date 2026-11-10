// t1_bcd_updown_top.sv: board top (Nexys A7-100T, master-XDC port names).
// Reference design for benchmark task t1_bcd_updown; DESIGN_ID "BCDU".
module t1_bcd_updown_top #(
    parameter int          CLKS_PER_BIT    = 868,
    parameter int          TIMEOUT_CYCLES  = 100_000,
    parameter int          DEBOUNCE_CYCLES = 1_000_000,
    parameter int          REFRESH_BITS    = 17,
    parameter logic [31:0] BUILD_STAMP     = 32'h0
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        BTNU,
    input  logic        BTND,
    input  logic [15:0] SW,
    output logic [15:0] LED,
    output logic        CA, CB, CC, CD, CE, CF, CG, DP,
    output logic [7:0]  AN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT
);
    logic        clk, rst, win_wr, win_rd;
    logic [6:0]  win_addr, seg_n;
    logic [31:0] win_wdata, win_rdata;
    logic [7:0][6:0] seg_lit;
    logic [7:0]  blank;

    assign clk = CLK100MHZ;
    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h4243_4455), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    bcd_updown #(.DEBOUNCE_CYCLES(DEBOUNCE_CYCLES)) u_ctr (
        .clk(clk), .rst(rst), .btn_up(BTNU), .btn_down(BTND), .sw_async(SW[1:0]),
        .led(LED), .seg_lit(seg_lit), .blank(blank),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    bm_scan8 #(.REFRESH_BITS(REFRESH_BITS)) u_scan (
        .clk(clk), .rst(rst), .enable(1'b1), .seg_lit(seg_lit), .blank(blank), .dp_lit(8'h00),
        .an(AN), .seg_n(seg_n), .dp_n(DP));
    assign {CG, CF, CE, CD, CC, CB, CA} = seg_n;
endmodule
