// v2_b_pdm_chain_top.sv: board top (Nexys A7-100T, master-XDC port names).
// Reference design for benchmark task v2_b_pdm_chain; DESIGN_ID "PDMC".
module v2_b_pdm_chain_top #(
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
    logic        clk_pc, rst_pc, win_wr_pc, win_rd_pc;
    logic [6:0]  win_addr_pc;
    logic [31:0] win_wdata_pc, win_rdata_pc;

    assign clk_pc = CLK100MHZ;
    reset_sync u_rst (.clk(clk_pc), .rst_n_async(CPU_RESETN), .rst(rst_pc));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h5044_4D43), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk_pc), .rst(rst_pc), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr_pc), .win_wr(win_wr_pc), .win_rd(win_rd_pc), .win_wdata(win_wdata_pc), .win_rdata(win_rdata_pc));

    pdm_chain #(.CLK_HALF(CLK_HALF)) u_core (
        .clk_pc(clk_pc), .rst_pc(rst_pc), .m_clk_pc(M_CLK), .m_data_pc(M_DATA), .m_lrsel_pc(M_LRSEL), .led_pc(LED),
        .win_addr_pc(win_addr_pc), .win_wr_pc(win_wr_pc), .win_rd_pc(win_rd_pc), .win_wdata_pc(win_wdata_pc), .win_rdata_pc(win_rdata_pc));
endmodule
