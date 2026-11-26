// Asynchronous FIFO: xpm_fifo_async, 1024 x 32 in one RAMB36 (Gray pointers inside the macro).
// The soak core limits the fill to 512 words itself, so the FIFO never fills.
module soak_fifo #(
    parameter int DEPTH = 1024,
    parameter int DW    = 32
) (
    input  logic          wr_clk,
    input  logic          rst,            // synchronous to wr_clk
    input  logic          wr_en,
    input  logic [DW-1:0] din,
    output logic          full,
    output logic          wr_rst_busy,
    output logic          overflow,
    output logic [$clog2(DEPTH):0] wr_data_count,
    input  logic          rd_clk,
    input  logic          rd_en,
    output logic [DW-1:0] dout,
    output logic          empty,
    output logic          rd_rst_busy,
    output logic          underflow
);
    xpm_fifo_async #(
        .CDC_SYNC_STAGES(2), .DOUT_RESET_VALUE(0), .ECC_MODE("no_ecc"), .FIFO_MEMORY_TYPE("distributed"),
        .FIFO_READ_LATENCY(1), .FIFO_WRITE_DEPTH(DEPTH), .FULL_RESET_VALUE(0), .PROG_EMPTY_THRESH(10),
        .PROG_FULL_THRESH(10), .RD_DATA_COUNT_WIDTH(1), .READ_DATA_WIDTH(DW), .READ_MODE("std"),
        .RELATED_CLOCKS(0), .SIM_ASSERT_CHK(0), .USE_ADV_FEATURES("0105"), .WAKEUP_TIME(0),
        .WRITE_DATA_WIDTH(DW), .WR_DATA_COUNT_WIDTH($clog2(DEPTH)+1)
    ) u_fifo (
        .sleep(1'b0), .rst(rst),
        .wr_clk(wr_clk), .wr_en(wr_en), .din(din), .full(full), .overflow(overflow),
        .wr_rst_busy(wr_rst_busy), .wr_data_count(wr_data_count),
        .rd_clk(rd_clk), .rd_en(rd_en), .dout(dout), .empty(empty), .underflow(underflow),
        .rd_rst_busy(rd_rst_busy),
        .injectsbiterr(1'b0), .injectdbiterr(1'b0)
    );
endmodule
