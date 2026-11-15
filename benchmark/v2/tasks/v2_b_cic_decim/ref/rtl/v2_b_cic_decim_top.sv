// v2_b_cic_decim_top.sv: board top (Nexys A7-100T, master-XDC port names).
// Reference design for benchmark task v2_b_cic_decim; DESIGN_ID "CICD".
module v2_b_cic_decim_top #(
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
    logic        clk_cd, rst_cd, win_wr_cd, win_rd_cd;
    logic [6:0]  win_addr_cd;
    logic [31:0] win_wdata_cd, win_rdata_cd;

    assign clk_cd = CLK100MHZ;
    assign LED = 16'd0;
    reset_sync u_rst (.clk(clk_cd), .rst_n_async(CPU_RESETN), .rst(rst_cd));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h4349_4344), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk_cd), .rst(rst_cd), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr_cd), .win_wr(win_wr_cd), .win_rd(win_rd_cd), .win_wdata(win_wdata_cd), .win_rdata(win_rdata_cd));

    cic_decim u_core (
        .clk_cd(clk_cd), .rst_cd(rst_cd),
        .win_addr_cd(win_addr_cd), .win_wr_cd(win_wr_cd), .win_rd_cd(win_rd_cd), .win_wdata_cd(win_wdata_cd), .win_rdata_cd(win_rdata_cd));
endmodule
