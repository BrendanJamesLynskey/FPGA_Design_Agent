// v2_b_pdm_front_top.sv: board top (Nexys A7-100T, master-XDC port names).
// Reference design for benchmark task v2_b_pdm_front; DESIGN_ID "PDMF".
module v2_b_pdm_front_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0,
    parameter int          CLK_HALF       = 16
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    output logic        M_CLK,
    input  logic        M_DATA,
    output logic        M_LRSEL,
    output logic [15:0] LED,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT
);
    logic        clk_pf, rst_pf, win_wr_pf, win_rd_pf;
    logic [6:0]  win_addr_pf;
    logic [31:0] win_wdata_pf, win_rdata_pf;

    assign clk_pf = CLK100MHZ;
    reset_sync u_rst (.clk(clk_pf), .rst_n_async(CPU_RESETN), .rst(rst_pf));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h5044_4D46), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk_pf), .rst(rst_pf), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr_pf), .win_wr(win_wr_pf), .win_rd(win_rd_pf), .win_wdata(win_wdata_pf), .win_rdata(win_rdata_pf));

    pdm_front #(.CLK_HALF(CLK_HALF)) u_core (
        .clk_pf(clk_pf), .rst_pf(rst_pf), .m_clk_pf(M_CLK), .m_data_pf(M_DATA), .m_lrsel_pf(M_LRSEL), .led_pf(LED),
        .win_addr_pf(win_addr_pf), .win_wr_pf(win_wr_pf), .win_rd_pf(win_rd_pf), .win_wdata_pf(win_wdata_pf), .win_rdata_pf(win_rdata_pf));
endmodule
