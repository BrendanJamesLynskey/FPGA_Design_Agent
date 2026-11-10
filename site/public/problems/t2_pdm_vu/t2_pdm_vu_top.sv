// t2_pdm_vu_top.sv: board top (Nexys A7-100T, master-XDC port names).
// Reference design for benchmark task t2_pdm_vu; DESIGN_ID "PDMV".
// PDM microphone level meter (M_LRSEL high, data at M_CLK falling edges), LED bar.
module t2_pdm_vu_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter int          CLK_HALF       = 20,
    parameter int          WINDOW         = 4096,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
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
    logic        clk, rst, win_wr, win_rd, mdata;
    logic [6:0]  win_addr;
    logic [31:0] win_wdata, win_rdata;

    assign clk = CLK100MHZ;
    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h5044_4D56), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    sync2 u_sync (.clk(clk), .rst(rst), .d(M_DATA), .q(mdata));

    always_ff @(posedge clk) begin
        if (rst) M_LRSEL <= 1'b1;
        else     M_LRSEL <= 1'b1;
    end

    pdm_vu #(.CLK_HALF(CLK_HALF), .WINDOW(WINDOW)) u_vu (
        .clk(clk), .rst(rst), .mdata(mdata), .mclk(M_CLK), .led(LED),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));
endmodule
