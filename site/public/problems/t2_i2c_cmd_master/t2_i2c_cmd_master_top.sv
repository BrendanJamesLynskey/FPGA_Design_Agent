// t2_i2c_cmd_master_top.sv: board top (Nexys A7-100T, master-XDC port names).
// Reference design for benchmark task t2_i2c_cmd_master; DESIGN_ID "I2CM".
// Byte-command I2C master on the ADT7420 bus (TMP_SCL / TMP_SDA, open drain).
module t2_i2c_cmd_master_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter int          QUARTER        = 250,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic CLK100MHZ,
    input  logic CPU_RESETN,
    inout  wire  TMP_SCL,
    inout  wire  TMP_SDA,
    input  logic UART_TXD_IN,
    output logic UART_RXD_OUT
);
    logic        clk, rst, win_wr, win_rd, scl_oe, sda_oe;
    logic [1:0]  lines;
    logic [6:0]  win_addr;
    logic [31:0] win_wdata, win_rdata;

    assign clk = CLK100MHZ;
    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h4932_434D), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    assign TMP_SCL = scl_oe ? 1'b0 : 1'bz;
    assign TMP_SDA = sda_oe ? 1'b0 : 1'bz;
    sync2 #(.WIDTH(2), .RESET_VALUE(2'b11)) u_sync (.clk(clk), .rst(rst), .d({TMP_SCL, TMP_SDA}), .q(lines));

    i2cm_regs #(.QUARTER(QUARTER)) u_regs (
        .clk(clk), .rst(rst), .scl_in(lines[1]), .sda_in(lines[0]), .scl_oe(scl_oe), .sda_oe(sda_oe),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));
endmodule
