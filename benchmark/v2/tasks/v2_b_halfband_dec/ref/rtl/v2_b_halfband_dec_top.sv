// v2_b_halfband_dec_top.sv: board top (Nexys A7-100T, master-XDC port names).
// Reference design for benchmark task v2_b_halfband_dec; DESIGN_ID "HBDC".
module v2_b_halfband_dec_top #(
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
    logic        clk_hb, rst_hb, win_wr_hb, win_rd_hb;
    logic [6:0]  win_addr_hb;
    logic [31:0] win_wdata_hb, win_rdata_hb;

    assign clk_hb = CLK100MHZ;
    assign LED = 16'd0;
    reset_sync u_rst (.clk(clk_hb), .rst_n_async(CPU_RESETN), .rst(rst_hb));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h4842_4443), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk_hb), .rst(rst_hb), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr_hb), .win_wr(win_wr_hb), .win_rd(win_rd_hb), .win_wdata(win_wdata_hb), .win_rdata(win_rdata_hb));

    halfband_dec u_core (
        .clk_hb(clk_hb), .rst_hb(rst_hb),
        .win_addr_hb(win_addr_hb), .win_wr_hb(win_wr_hb), .win_rd_hb(win_rd_hb), .win_wdata_hb(win_wdata_hb), .win_rdata_hb(win_rdata_hb));
endmodule
