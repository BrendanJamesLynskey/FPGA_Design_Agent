// v2_b_comp_fir_top.sv: board top (Nexys A7-100T, master-XDC port names).
// Reference design for benchmark task v2_b_comp_fir; DESIGN_ID "CFIR".
module v2_b_comp_fir_top #(
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
    logic        clk_cf, rst_cf, win_wr_cf, win_rd_cf;
    logic [6:0]  win_addr_cf;
    logic [31:0] win_wdata_cf, win_rdata_cf;

    assign clk_cf = CLK100MHZ;
    assign LED = 16'd0;
    reset_sync u_rst (.clk(clk_cf), .rst_n_async(CPU_RESETN), .rst(rst_cf));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h4346_4952), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk_cf), .rst(rst_cf), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr_cf), .win_wr(win_wr_cf), .win_rd(win_rd_cf), .win_wdata(win_wdata_cf), .win_rdata(win_rdata_cf));

    comp_fir u_core (
        .clk_cf(clk_cf), .rst_cf(rst_cf),
        .win_addr_cf(win_addr_cf), .win_wr_cf(win_wr_cf), .win_rd_cf(win_rd_cf), .win_wdata_cf(win_wdata_cf), .win_rdata_cf(win_rdata_cf));
endmodule
