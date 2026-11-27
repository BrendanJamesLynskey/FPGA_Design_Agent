// fifo: 512 x 32 asynchronous FIFO (xpm_fifo_async, Gray-coded pointers, 2-flop synchronisers, first-word-fall-through).
// The only module of the design that holds both FIFO clocks; it contains no registers of its own.
// Memory is distributed RAM: the flow's FIFO memory exception (flow/xpm_cdc.tcl) matches RAM cells with CLK/WCLK
// pins (distributed RAM, URAM); a RAMB18E2 (CLKARDCLK/CLKBWRCLK) is not matched and fails the build.
module fifo #(
    parameter int DEPTH = 512,
    parameter int CW    = 10
) (
    input  logic          rst,
    input  logic          wr_clk,
    input  logic          wr_en,
    input  logic [31:0]   din,
    output logic          full,
    output logic          wr_rst_busy,
    output logic [CW-1:0] wr_data_count,
    input  logic          rd_clk,
    input  logic          rd_en,
    output logic [31:0]   dout,
    output logic          empty,
    output logic          rd_rst_busy
);
    xpm_fifo_async #(
        .CDC_SYNC_STAGES(2), .DOUT_RESET_VALUE("0"), .ECC_MODE("no_ecc"), .FIFO_MEMORY_TYPE("distributed"),
        .FIFO_READ_LATENCY(0), .FIFO_WRITE_DEPTH(DEPTH), .FULL_RESET_VALUE(0),
        .READ_DATA_WIDTH(32), .READ_MODE("fwft"), .RELATED_CLOCKS(0), .SIM_ASSERT_CHK(0),
        .USE_ADV_FEATURES("0004"), .WAKEUP_TIME(0), .WRITE_DATA_WIDTH(32), .WR_DATA_COUNT_WIDTH(CW)
    ) u_fifo (
        .sleep(1'b0), .rst(rst),
        .wr_clk(wr_clk), .wr_en(wr_en), .din(din), .full(full),
        .wr_rst_busy(wr_rst_busy), .wr_data_count(wr_data_count),
        .rd_clk(rd_clk), .rd_en(rd_en), .dout(dout), .empty(empty), .rd_rst_busy(rd_rst_busy),
        .injectsbiterr(1'b0), .injectdbiterr(1'b0));
endmodule
