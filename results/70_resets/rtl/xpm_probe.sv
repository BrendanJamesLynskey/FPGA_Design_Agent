// Brief 70 Part 2c: AMD's XPM macros instantiated with default reset settings, to see what their synthesised netlists do with
// a reset (cell types of the flip-flops, what drives them). Synthesised out of context; nothing here is simulated.
module xp_fifo_sync (input logic clk, input logic rst, input logic wr_en, input logic [31:0] din, input logic rd_en,
                     output logic [31:0] dout, output logic empty, output logic full);
  xpm_fifo_sync #(.FIFO_MEMORY_TYPE("block"), .FIFO_WRITE_DEPTH(512), .WRITE_DATA_WIDTH(32), .READ_DATA_WIDTH(32),
                  .READ_MODE("std"), .USE_ADV_FEATURES("0000")) u (
    .sleep(1'b0), .rst(rst), .wr_clk(clk), .wr_en(wr_en), .din(din), .full(full), .rd_en(rd_en), .dout(dout), .empty(empty),
    .injectsbiterr(1'b0), .injectdbiterr(1'b0));
endmodule
module xp_fifo_async (input logic wr_clk, input logic rd_clk, input logic rst, input logic wr_en, input logic [31:0] din,
                      input logic rd_en, output logic [31:0] dout, output logic empty, output logic full);
  xpm_fifo_async #(.FIFO_MEMORY_TYPE("block"), .FIFO_WRITE_DEPTH(512), .WRITE_DATA_WIDTH(32), .READ_DATA_WIDTH(32),
                   .READ_MODE("std"), .USE_ADV_FEATURES("0000")) u (
    .sleep(1'b0), .rst(rst), .wr_clk(wr_clk), .wr_en(wr_en), .din(din), .full(full), .rd_clk(rd_clk), .rd_en(rd_en),
    .dout(dout), .empty(empty), .injectsbiterr(1'b0), .injectdbiterr(1'b0));
endmodule
module xp_rst_async (input logic clk, input logic arst, output logic rst_out);
  xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u (.dest_arst(rst_out), .dest_clk(clk), .src_arst(arst));
endmodule
module xp_rst_sync (input logic clk, input logic src_rst, output logic rst_out);
  xpm_cdc_sync_rst #(.DEST_SYNC_FF(4), .INIT(1)) u (.dest_rst(rst_out), .dest_clk(clk), .src_rst(src_rst));
endmodule
module xp_mem_ram (input logic clk, input logic rst, input logic we, input logic [9:0] wa, input logic [9:0] ra,
                   input logic [31:0] din, output logic [31:0] dout);
  xpm_memory_sdpram #(.ADDR_WIDTH_A(10), .ADDR_WIDTH_B(10), .BYTE_WRITE_WIDTH_A(32), .MEMORY_SIZE(32768), .READ_DATA_WIDTH_B(32),
                      .WRITE_DATA_WIDTH_A(32), .READ_LATENCY_B(2), .RST_MODE_B("SYNC"), .MEMORY_PRIMITIVE("block")) u (
    .clka(clk), .clkb(clk), .ena(1'b1), .enb(1'b1), .wea(we), .addra(wa), .addrb(ra), .dina(din), .doutb(dout),
    .rstb(rst), .regceb(1'b1), .sleep(1'b0), .injectsbiterra(1'b0), .injectdbiterra(1'b0));
endmodule
