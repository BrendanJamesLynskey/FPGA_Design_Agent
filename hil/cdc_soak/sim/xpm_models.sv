`timescale 1ns / 1ps
// xpm_models.sv: behavioural stand-ins for the five XPM macros the rig uses, for Icarus only (CDC_SIM).
// Written from the port lists and the behaviour described in AMD UG974; NOT AMD's source. Vivado builds use the
// real macros. The first destination flop of every crossing is a cff with injection, as in the hand-built variants,
// so the XPM variants see the same metastability model. These models are what the simulation of C3/C5/C7/C9/C11
// and of the readout path checks against; the hardware run is what checks the real macros.

module xpm_cdc_single #(
    parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0, parameter integer SIM_ASSERT_CHK = 0,
    parameter integer SRC_INPUT_REG = 1, parameter integer VERSION = 0
) (
    input wire src_clk, input wire src_in, input wire dest_clk, output wire dest_out
);
    logic s = 1'b0;
    always_ff @(posedge src_clk) s <= src_in;
    sync_n #(.W(1), .STAGES(DEST_SYNC_FF)) u (.clk(dest_clk), .d(SRC_INPUT_REG ? s : src_in), .q(dest_out));
endmodule

module xpm_cdc_pulse #(
    parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0, parameter integer REG_OUTPUT = 0,
    parameter integer RST_USED = 1, parameter integer SIM_ASSERT_CHK = 0, parameter integer VERSION = 0
) (
    input wire src_clk, input wire src_pulse, input wire dest_clk, input wire src_rst, input wire dest_rst,
    output wire dest_pulse
);
    logic sp = 1'b0, lvl = 1'b0, dq = 1'b0, po = 1'b0;
    logic dl;
    always_ff @(posedge src_clk) begin
        sp <= src_pulse;
        if (src_pulse && !sp) lvl <= ~lvl;
    end
    sync_n #(.W(1), .STAGES(DEST_SYNC_FF)) u (.clk(dest_clk), .d(lvl), .q(dl));
    always_ff @(posedge dest_clk) begin dq <= dl; po <= dl ^ dq; end
    assign dest_pulse = REG_OUTPUT ? po : (dl ^ dq);
endmodule

module xpm_cdc_gray #(
    parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0, parameter integer REG_OUTPUT = 0,
    parameter integer SIM_ASSERT_CHK = 0, parameter integer SIM_LOSSLESS_GRAY_CHK = 0, parameter integer VERSION = 0,
    parameter integer WIDTH = 2
) (
    input wire src_clk, input wire [WIDTH-1:0] src_in_bin, input wire dest_clk, output wire [WIDTH-1:0] dest_out_bin
);
    logic [WIDTH-1:0] g = '0, dg, o = '0;
    wire  [WIDTH-1:0] b;
    always_ff @(posedge src_clk) g <= src_in_bin ^ (src_in_bin >> 1);
    sync_n #(.W(WIDTH), .STAGES(DEST_SYNC_FF)) u (.clk(dest_clk), .d(g), .q(dg));
    for (genvar i = 0; i < WIDTH; i++) begin : dec
        assign b[i] = ^dg[WIDTH-1:i];
    end
    always_ff @(posedge dest_clk) o <= b;
    assign dest_out_bin = REG_OUTPUT ? o : b;
endmodule

module xpm_cdc_handshake #(
    parameter integer DEST_EXT_HSK = 1, parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0,
    parameter integer SIM_ASSERT_CHK = 0, parameter integer SRC_SYNC_FF = 4, parameter integer VERSION = 0,
    parameter integer WIDTH = 1
) (
    input wire src_clk, input wire [WIDTH-1:0] src_in, input wire src_send, output wire src_rcv,
    input wire dest_clk, output wire [WIDTH-1:0] dest_out, output wire dest_req, input wire dest_ack
);
    logic [WIDTH-1:0] hs = '0, dh = '0;
    logic sd = 1'b0, dr = 1'b0, dsend;
    always_ff @(posedge src_clk) begin
        sd <= src_send;
        if (src_send && !sd) hs <= src_in;
    end
    sync_n #(.W(1), .STAGES(DEST_SYNC_FF)) u_req (.clk(dest_clk), .d(sd), .q(dsend));
    always_ff @(posedge dest_clk) begin
        dr <= dsend;
        if (dsend && !dr) dh <= hs;
    end
    sync_n #(.W(1), .STAGES(SRC_SYNC_FF)) u_ack (.clk(src_clk), .d(dest_ack), .q(src_rcv));
    assign dest_out = dh;
    assign dest_req = dr;
endmodule

// Asynchronous FIFO, "std" read mode, latency 1. rst (write domain) resets the read side first, through a
// request/acknowledge pair, and only then the write pointer, so the read side never sees a pointer jump while it is
// still reading; wr_rst_busy and rd_rst_busy cover the whole sequence.
module xpm_fifo_async #(
    parameter FIFO_MEMORY_TYPE = "auto", parameter ECC_MODE = "no_ecc", parameter integer RELATED_CLOCKS = 0,
    parameter integer SIM_ASSERT_CHK = 0, parameter EN_SIM_ASSERT_ERR = "warning", parameter integer CASCADE_HEIGHT = 0,
    parameter integer FIFO_WRITE_DEPTH = 2048, parameter integer WRITE_DATA_WIDTH = 32,
    parameter integer WR_DATA_COUNT_WIDTH = 1, parameter integer PROG_FULL_THRESH = 10,
    parameter integer FULL_RESET_VALUE = 0, parameter USE_ADV_FEATURES = "0707", parameter READ_MODE = "std",
    parameter integer FIFO_READ_LATENCY = 1, parameter integer READ_DATA_WIDTH = WRITE_DATA_WIDTH,
    parameter integer RD_DATA_COUNT_WIDTH = 1, parameter integer PROG_EMPTY_THRESH = 10,
    parameter DOUT_RESET_VALUE = "0", parameter integer CDC_SYNC_STAGES = 2, parameter WAKEUP_TIME = 0
) (
    input wire sleep, input wire rst, input wire wr_clk, input wire wr_en, input wire [WRITE_DATA_WIDTH-1:0] din,
    output wire full, output wire prog_full, output wire [WR_DATA_COUNT_WIDTH-1:0] wr_data_count,
    output wire overflow, output wire wr_rst_busy, output wire almost_full, output wire wr_ack,
    input wire rd_clk, input wire rd_en, output wire [READ_DATA_WIDTH-1:0] dout, output wire empty,
    output wire prog_empty, output wire [RD_DATA_COUNT_WIDTH-1:0] rd_data_count, output wire underflow,
    output wire rd_rst_busy, output wire almost_empty, output wire data_valid,
    input wire injectsbiterr, input wire injectdbiterr, output wire sbiterr, output wire dbiterr
);
    localparam int AW = $clog2(FIFO_WRITE_DEPTH);
    logic [WRITE_DATA_WIDTH-1:0] mem [FIFO_WRITE_DEPTH];
    logic [AW:0] wbin = '0, wg = '0, rbin = '0, rg = '0, rq, wq;
    logic wbusy = 1'b1, wreq = 1'b1, rbusy = 1'b0, rack = 1'b0, wfull = 1'b0, rempty = 1'b1;
    logic rreq_s, rack_s;
    logic [2:0] rhold = '1;
    logic [READ_DATA_WIDTH-1:0] q = '0;
    sync_n #(.W(1), .STAGES(CDC_SYNC_STAGES)) u_rq (.clk(rd_clk), .d(wreq), .q(rreq_s));
    sync_n #(.W(1), .STAGES(CDC_SYNC_STAGES)) u_ak (.clk(wr_clk), .d(rack), .q(rack_s));
    sync_n #(.W(AW+1), .STAGES(CDC_SYNC_STAGES)) u_wp (.clk(rd_clk), .d(wg), .q(wq));
    sync_n #(.W(AW+1), .STAGES(CDC_SYNC_STAGES)) u_rp (.clk(wr_clk), .d(rg), .q(rq));
    // write side
    wire [AW:0] wbn = wbin + (AW+1)'(wr_en & ~wfull & ~wbusy);
    wire [AW:0] wgn = (wbn >> 1) ^ wbn;
    always_ff @(posedge wr_clk) begin
        if (rst) begin wbusy <= 1'b1; wreq <= 1'b1; wfull <= 1'b1; end
        else if (wreq && rack_s) begin wbin <= '0; wg <= '0; wreq <= 1'b0; end
        else if (!wreq && !rack_s && wbusy) begin wbusy <= 1'b0; wfull <= 1'b0; end
        else if (!wbusy) begin
            if (wr_en && !wfull) mem[wbin[AW-1:0]] <= din;
            wbin <= wbn; wg <= wgn;
            wfull <= wgn == {~rq[AW:AW-1], rq[AW-2:0]};
        end
    end
    // read side
    wire [AW:0] rbn = rbin + (AW+1)'(rd_en & ~rempty & ~rbusy);
    wire [AW:0] rgn = (rbn >> 1) ^ rbn;
    // A reset request first raises rd_rst_busy (a read on that edge is still done, as rd_rst_busy was low when the
    // user sampled it); the pointers are reset on a later edge, once rd_rst_busy is visible.
    always_ff @(posedge rd_clk) begin
        if (rreq_s && rbusy) begin rack <= 1'b1; rbin <= '0; rg <= '0; rempty <= 1'b1; rhold <= '1; end
        else if (rack) rack <= 1'b0;
        else if (!rreq_s && rhold != 0) rhold <= rhold - 1'b1;
        else if (!rreq_s && rbusy && rhold == 0) rbusy <= 1'b0;
        else if (!rbusy) begin
            if (rreq_s) rbusy <= 1'b1;
            if (rd_en && !rempty) q <= mem[rbin[AW-1:0]];
            rbin <= rbn; rg <= rgn;
            rempty <= rgn == wq;
        end
    end
    assign full = wfull; assign empty = rempty; assign dout = q;
    assign wr_rst_busy = wbusy; assign rd_rst_busy = rbusy;
    assign prog_full = 1'b0; assign wr_data_count = '0; assign overflow = 1'b0; assign almost_full = 1'b0;
    assign wr_ack = 1'b0; assign prog_empty = 1'b0; assign rd_data_count = '0; assign underflow = 1'b0;
    assign almost_empty = 1'b0; assign data_valid = 1'b0; assign sbiterr = 1'b0; assign dbiterr = 1'b0;
endmodule
