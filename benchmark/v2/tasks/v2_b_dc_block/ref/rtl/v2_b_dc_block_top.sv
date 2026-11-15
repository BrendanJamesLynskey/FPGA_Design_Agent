// v2_b_dc_block_top.sv: board top (Nexys A7-100T, master-XDC port names).
// Reference design for benchmark task v2_b_dc_block; DESIGN_ID "DCBK".
module v2_b_dc_block_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    output logic [15:0] LED,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT
);
    logic        clk_db, rst_db, win_wr_db, win_rd_db;
    logic [6:0]  win_addr_db;
    logic [31:0] win_wdata_db, win_rdata_db;

    assign clk_db = CLK100MHZ;
    assign LED = 16'd0;
    reset_sync u_rst (.clk(clk_db), .rst_n_async(CPU_RESETN), .rst(rst_db));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h4443_424B), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk_db), .rst(rst_db), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr_db), .win_wr(win_wr_db), .win_rd(win_rd_db), .win_wdata(win_wdata_db), .win_rdata(win_rdata_db));

    dc_block u_core (
        .clk_db(clk_db), .rst_db(rst_db),
        .win_addr_db(win_addr_db), .win_wr_db(win_wr_db), .win_rd_db(win_rd_db), .win_wdata_db(win_wdata_db), .win_rdata_db(win_rdata_db));
endmodule
