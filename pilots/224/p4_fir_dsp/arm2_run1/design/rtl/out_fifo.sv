// Output FIFO: written on clk_dp (FIR results), read on clk_bus (OUT_POP). 2048 deep in one
// BRAM36; the datapath limits the occupancy to 1024. First-word-fall-through.
module out_fifo (
    input  logic        rst,        // synchronous to wr_clk, held several cycles
    input  logic        wr_clk,
    input  logic        wr_en,
    input  logic [15:0] din,
    output logic [11:0] wr_count,
    input  logic        rd_clk,
    input  logic        rd_en,
    output logic [15:0] dout,
    output logic        empty,
    output logic [11:0] rd_count
);
    logic full_u, wr_busy_u;
    /* verilator lint_off PINCONNECTEMPTY */
    xpm_fifo_async #(
        .CDC_SYNC_STAGES(2), .ECC_MODE("no_ecc"), .FIFO_MEMORY_TYPE("block"),
        .FIFO_READ_LATENCY(0), .FIFO_WRITE_DEPTH(2048), .FULL_RESET_VALUE(0),
        .READ_DATA_WIDTH(16), .READ_MODE("fwft"), .RD_DATA_COUNT_WIDTH(12),
        .RELATED_CLOCKS(0), .USE_ADV_FEATURES("0404"), .WRITE_DATA_WIDTH(16),
        .WR_DATA_COUNT_WIDTH(12)
    ) u_fifo (
        .sleep(1'b0), .rst(rst),
        .wr_clk(wr_clk), .wr_en(wr_en), .din(din), .full(full_u),
        .wr_rst_busy(wr_busy_u), .wr_data_count(wr_count),
        .rd_clk(rd_clk), .rd_en(rd_en), .dout(dout), .empty(empty),
        .rd_rst_busy(), .rd_data_count(rd_count),
        .injectsbiterr(1'b0), .injectdbiterr(1'b0)
    );
    /* verilator lint_on PINCONNECTEMPTY */
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_flags;
    assign unused_flags = full_u ^ wr_busy_u;
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
