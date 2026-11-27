// 512 x 32 asynchronous FIFO (xpm_fifo_async, FWFT): gray pointers and synchronisers are inside the macro.
module async_fifo #(
    parameter int DEPTH = 512,
    parameter int DATA_WIDTH = 32,
    parameter int ADDR_WIDTH = 9,
    parameter int SYNC_STAGES = 2
) (
    input  logic                    rst,        // active high, wr_clk domain
    input  logic                    wr_clk,
    input  logic                    wr_en,
    input  logic [DATA_WIDTH-1:0]   din,
    output logic                    full,
    output logic [ADDR_WIDTH:0]     wr_count,
    output logic                    wr_busy,
    output logic                    overflow,
    input  logic                    rd_clk,
    input  logic                    rd_en,
    output logic [DATA_WIDTH-1:0]   dout,
    output logic                    empty,
    output logic                    rd_busy,
    output logic                    underflow
);
    xpm_fifo_async #(
        .CDC_SYNC_STAGES(SYNC_STAGES), .DOUT_RESET_VALUE("0"), .ECC_MODE("no_ecc"),
        .FIFO_MEMORY_TYPE("distributed"), .FIFO_READ_LATENCY(0), .FIFO_WRITE_DEPTH(DEPTH),
        .FULL_RESET_VALUE(0), .PROG_EMPTY_THRESH(10), .PROG_FULL_THRESH(10),
        .RD_DATA_COUNT_WIDTH(ADDR_WIDTH + 1), .READ_DATA_WIDTH(DATA_WIDTH), .READ_MODE("fwft"),
        .RELATED_CLOCKS(0), .SIM_ASSERT_CHK(0), .USE_ADV_FEATURES("0105"), .WAKEUP_TIME(0),
        .WRITE_DATA_WIDTH(DATA_WIDTH), .WR_DATA_COUNT_WIDTH(ADDR_WIDTH + 1)
    ) u_fifo (
        .rst(rst), .sleep(1'b0),
        .wr_clk(wr_clk), .wr_en(wr_en), .din(din), .full(full), .wr_data_count(wr_count),
        .wr_rst_busy(wr_busy), .overflow(overflow),
        .rd_clk(rd_clk), .rd_en(rd_en), .dout(dout), .empty(empty), .rd_rst_busy(rd_busy),
        .underflow(underflow),
        .injectsbiterr(1'b0), .injectdbiterr(1'b0));
endmodule
