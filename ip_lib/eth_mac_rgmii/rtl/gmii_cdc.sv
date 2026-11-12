// gmii_cdc.sv: one port's received bytes from its RX_CLK domain into the core clock domain.
// Write side: every byte (gmii_v) with its RX_ER, and an end token when RX_DV falls. Read side: an entry
// whenever the FIFO is not empty, so the core sees the frame with occasional gaps (the two 125 MHz clocks differ by
// up to 200 ppm; the inter-frame gap absorbs it). xpm_fifo_async, 16 deep, 2 synchroniser stages.
// rx_clk_cnt: a count of RX_CLK edges, carried over in Gray code, for the host to check the clock frequency.

module gmii_cdc (
    input  logic        rx_clk,
    input  logic        rx_rst,         // synchronous to rx_clk
    input  logic [7:0]  gmii_d,
    input  logic        gmii_v,         // a byte this clock
    input  logic        gmii_dv,        // the frame is active (its fall writes the end token)
    input  logic        gmii_er,
    input  logic        clk,
    output logic        o_v,
    output logic        o_eof,
    output logic        o_er,
    output logic [7:0]  o_d,
    output logic        o_ovf,          // one clock: an entry was lost (FIFO full)
    output logic [31:0] o_rxclk_cnt
);
    logic       dv_q;
    logic       wr;
    logic [9:0] din, dout;
    logic       full, empty, rd_q, ovf_w;
    always_ff @(posedge rx_clk) dv_q <= rx_rst ? 1'b0 : gmii_dv;
    assign wr  = gmii_v || (dv_q && !gmii_dv);
    assign din = gmii_v ? {1'b0, gmii_er, gmii_d} : {1'b1, 1'b0, 8'h00};
    assign ovf_w = wr && full;

    xpm_fifo_async #(
        .FIFO_MEMORY_TYPE("distributed"), .FIFO_WRITE_DEPTH(16), .WRITE_DATA_WIDTH(10), .READ_DATA_WIDTH(10),
        .READ_MODE("std"), .FIFO_READ_LATENCY(1), .CDC_SYNC_STAGES(2), .USE_ADV_FEATURES("0000"),
        .WR_DATA_COUNT_WIDTH(1), .RD_DATA_COUNT_WIDTH(1), .DOUT_RESET_VALUE("0"), .ECC_MODE("no_ecc"),
        .RELATED_CLOCKS(0), .SIM_ASSERT_CHK(0), .WAKEUP_TIME(0), .FULL_RESET_VALUE(0),
        .PROG_EMPTY_THRESH(10), .PROG_FULL_THRESH(10), .CASCADE_HEIGHT(0), .EN_SIM_ASSERT_ERR("warning")
    ) u_fifo (
        .sleep(1'b0), .rst(rx_rst), .wr_clk(rx_clk), .wr_en(wr && !full), .din(din), .full(full), .prog_full(),
        .wr_data_count(), .overflow(), .wr_rst_busy(), .almost_full(), .wr_ack(),
        .rd_clk(clk), .rd_en(!empty), .dout(dout), .empty(empty), .prog_empty(), .rd_data_count(), .underflow(),
        .rd_rst_busy(), .almost_empty(), .data_valid(), .injectsbiterr(1'b0), .injectdbiterr(1'b0), .sbiterr(),
        .dbiterr());
    always_ff @(posedge clk) rd_q <= !empty;
    assign o_v   = rd_q;
    assign o_eof = dout[9];
    assign o_er  = dout[8];
    assign o_d   = dout[7:0];

    xpm_cdc_pulse #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_ovf (
        .src_clk(rx_clk), .src_pulse(ovf_w), .src_rst(1'b0), .dest_clk(clk), .dest_pulse(o_ovf), .dest_rst(1'b0));

    logic [31:0] cnt;
    always_ff @(posedge rx_clk) cnt <= rx_rst ? 32'd0 : cnt + 32'd1;
    xpm_cdc_gray #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .SIM_ASSERT_CHK(0),
                   .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(32)) u_cnt (
        .src_clk(rx_clk), .src_in_bin(cnt), .dest_clk(clk), .dest_out_bin(o_rxclk_cnt));
endmodule
