// C11: xpm_fifo_async, 512 x 16.
module cdcfx_c11 (input logic clk_a, input logic clk_b, input logic rst, input logic winc, input logic [15:0] wdata,
                  output logic wfull, input logic rinc, output logic [15:0] rdata, output logic rempty);
    logic wbusy, rbusy, full, empty;
    xpm_fifo_async #(.FIFO_MEMORY_TYPE("block"), .FIFO_WRITE_DEPTH(512), .WRITE_DATA_WIDTH(16), .READ_DATA_WIDTH(16),
                     .READ_MODE("std"), .FIFO_READ_LATENCY(1), .CDC_SYNC_STAGES(2), .USE_ADV_FEATURES("0000"),
                     .DOUT_RESET_VALUE("0"))
        u_fifo (.sleep(1'b0), .rst(rst), .wr_clk(clk_a), .wr_en(winc), .din(wdata), .full(full), .prog_full(),
                .wr_data_count(), .overflow(), .wr_rst_busy(wbusy), .almost_full(), .wr_ack(), .rd_clk(clk_b),
                .rd_en(rinc), .dout(rdata), .empty(empty), .prog_empty(), .rd_data_count(), .underflow(),
                .rd_rst_busy(rbusy), .almost_empty(), .data_valid(), .injectsbiterr(1'b0), .injectdbiterr(1'b0),
                .sbiterr(), .dbiterr());
    assign wfull = full | wbusy;
    assign rempty = empty | rbusy;
endmodule
