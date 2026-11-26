// Simulation-only stand-ins for Xilinx primitives and XPM macros (Vivado supplies the real ones).
`ifndef SYNTHESIS
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off DECLFILENAME */
/* verilator lint_off MULTITOP */
/* verilator lint_off PROCASSINIT */
/* verilator lint_off SYNCASYNCNET */
/* verilator lint_off BLKSEQ */
/* verilator lint_off WIDTHEXPAND */
/* verilator lint_off WIDTHTRUNC */
/* verilator lint_off WIDTHCONCAT */
/* verilator lint_off SYNCASYNCNET */
/* verilator lint_off BLKSEQ */

module xpm_cdc_single #(
    parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0,
    parameter integer SIM_ASSERT_CHK = 0, parameter integer SRC_INPUT_REG = 1
) (
    input  logic src_clk, input logic src_in, input logic dest_clk, output logic dest_out
);
    logic s;
    logic [DEST_SYNC_FF-1:0] ch = '0;
    always_ff @(posedge src_clk) s <= src_in;
    wire d = (SRC_INPUT_REG != 0) ? s : src_in;
    always_ff @(posedge dest_clk) ch <= {ch[DEST_SYNC_FF-2:0], d};
    assign dest_out = ch[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_array_single #(
    parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0,
    parameter integer SIM_ASSERT_CHK = 0, parameter integer SRC_INPUT_REG = 1,
    parameter integer WIDTH = 2
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in,
    input  logic dest_clk, output logic [WIDTH-1:0] dest_out
);
    logic [WIDTH-1:0] ch [DEST_SYNC_FF];
    always_ff @(posedge dest_clk) begin
        ch[0] <= src_in;
        for (int i = 1; i < DEST_SYNC_FF; i++) ch[i] <= ch[i-1];
    end
    assign dest_out = ch[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_gray #(
    parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0,
    parameter integer REG_OUTPUT = 0, parameter integer SIM_ASSERT_CHK = 0,
    parameter integer SIM_LOSSLESS_GRAY_CHK = 0, parameter integer WIDTH = 2
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in_bin,
    input  logic dest_clk, output logic [WIDTH-1:0] dest_out_bin
);
    logic [WIDTH-1:0] g;
    logic [WIDTH-1:0] ch [DEST_SYNC_FF];
    always_ff @(posedge src_clk) g <= src_in_bin ^ (src_in_bin >> 1);
    always_ff @(posedge dest_clk) begin
        ch[0] <= g;
        for (int i = 1; i < DEST_SYNC_FF; i++) ch[i] <= ch[i-1];
    end
    always_comb begin
        dest_out_bin[WIDTH-1] = ch[DEST_SYNC_FF-1][WIDTH-1];
        for (int i = WIDTH-2; i >= 0; i--) dest_out_bin[i] = dest_out_bin[i+1] ^ ch[DEST_SYNC_FF-1][i];
    end
endmodule

module xpm_cdc_pulse #(
    parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0,
    parameter integer REG_OUTPUT = 0, parameter integer RST_USED = 1,
    parameter integer SIM_ASSERT_CHK = 0
) (
    input  logic src_clk, input logic src_rst, input logic src_pulse,
    input  logic dest_clk, input logic dest_rst, output logic dest_pulse
);
    logic tog = 1'b0;
    logic [DEST_SYNC_FF-1:0] ch = '0;
    logic prev = 1'b0;
    always_ff @(posedge src_clk) if (src_pulse) tog <= ~tog;
    always_ff @(posedge dest_clk) begin
        ch <= {ch[DEST_SYNC_FF-2:0], tog};
        prev <= ch[DEST_SYNC_FF-1];
    end
    assign dest_pulse = ch[DEST_SYNC_FF-1] ^ prev;
endmodule

module xpm_cdc_async_rst #(
    parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0,
    parameter integer RST_ACTIVE_HIGH = 0
) (
    output logic dest_arst, input logic dest_clk, input logic src_arst
);
    logic [DEST_SYNC_FF-1:0] ch = '1;
    wire a = (RST_ACTIVE_HIGH != 0) ? src_arst : ~src_arst;
    always_ff @(posedge dest_clk)
        if (a) ch <= '1; else ch <= {ch[DEST_SYNC_FF-2:0], 1'b0};
    assign dest_arst = (RST_ACTIVE_HIGH != 0) ? ch[DEST_SYNC_FF-1] : ~ch[DEST_SYNC_FF-1];
endmodule

module xpm_fifo_async #(
    parameter integer CDC_SYNC_STAGES = 2, parameter ECC_MODE = "no_ecc",
    parameter FIFO_MEMORY_TYPE = "auto", parameter integer FIFO_READ_LATENCY = 1,
    parameter integer FIFO_WRITE_DEPTH = 2048, parameter integer FULL_RESET_VALUE = 0,
    parameter integer READ_DATA_WIDTH = 32, parameter READ_MODE = "std",
    parameter integer RD_DATA_COUNT_WIDTH = 1, parameter integer RELATED_CLOCKS = 0,
    parameter USE_ADV_FEATURES = "0707", parameter integer WRITE_DATA_WIDTH = 32,
    parameter integer WR_DATA_COUNT_WIDTH = 1
) (
    input  logic sleep, input logic rst,
    input  logic wr_clk, input logic wr_en, input logic [WRITE_DATA_WIDTH-1:0] din,
    output logic full, output logic wr_rst_busy, output logic [WR_DATA_COUNT_WIDTH-1:0] wr_data_count,
    input  logic rd_clk, input logic rd_en, output logic [READ_DATA_WIDTH-1:0] dout,
    output logic empty, output logic rd_rst_busy, output logic [RD_DATA_COUNT_WIDTH-1:0] rd_data_count,
    input  logic injectsbiterr, input logic injectdbiterr
);
    localparam integer AW = $clog2(FIFO_WRITE_DEPTH) + 1;
    logic [WRITE_DATA_WIDTH-1:0] mem [0:FIFO_WRITE_DEPTH-1];
    logic [AW-1:0] wptr = '0, rptr = '0, w1 = '0, w2 = '0, r1 = '0, r2 = '0;
    logic [2:0] rst_w = '0, rst_r = '0;
    always_ff @(posedge wr_clk) rst_w <= {rst_w[1:0], rst};
    always_ff @(posedge rd_clk) rst_r <= {rst_r[1:0], rst};
    assign wr_rst_busy = rst | (|rst_w);
    assign rd_rst_busy = rst_r[0] | rst_r[1] | rst_r[2];
    // write-side count lags the write pointer by 4 clocks (as the real macro's count does)
    logic [AW-1:0] wc0 = '0, wc1 = '0, wc2 = '0, wc3 = '0;
    always_ff @(posedge wr_clk) begin
        wc0 <= wptr - r2; wc1 <= wc0; wc2 <= wc1; wc3 <= wc2;
    end
    wire [AW-1:0] wcnt = wc3;
    wire [AW-1:0] rcnt = w2 - rptr;
    assign full = (wcnt >= FIFO_WRITE_DEPTH);
    assign empty = (rcnt == 0) | rd_rst_busy;
    assign dout = mem[rptr[AW-2:0]];
    assign wr_data_count = wcnt[WR_DATA_COUNT_WIDTH-1:0];
    assign rd_data_count = rcnt[RD_DATA_COUNT_WIDTH-1:0];
    always_ff @(posedge wr_clk) begin
        r1 <= rptr; r2 <= r1;
        if (rst) wptr <= '0;
        else if (wr_en && !full && !wr_rst_busy) begin
            mem[wptr[AW-2:0]] <= din;
            wptr <= wptr + 1'b1;
        end
    end
    always_ff @(posedge rd_clk) begin
        w1 <= wptr; w2 <= w1;
        if (rst_r[1] | rst_r[0]) rptr <= '0;
        else if (rd_en && !empty) rptr <= rptr + 1'b1;
    end
endmodule

module USR_ACCESSE2 (output logic [31:0] DATA, output logic CFGCLK, output logic DATAVALID);
    assign DATA = 32'h0;
    assign CFGCLK = 1'b0;
    assign DATAVALID = 1'b1;
endmodule

module MMCME4_BASE #(
    parameter BANDWIDTH = "OPTIMIZED", parameter real CLKFBOUT_MULT_F = 5.0,
    parameter real CLKIN1_PERIOD = 0.0, parameter real CLKOUT0_DIVIDE_F = 1.0,
    parameter integer DIVCLK_DIVIDE = 1
) (
    input logic CLKIN1, input logic CLKFBIN, input logic PWRDWN, input logic RST,
    output logic CLKOUT0, output logic CLKFBOUT, output logic LOCKED
);
    assign CLKOUT0 = CLKIN1;
    assign CLKFBOUT = CLKIN1;
    assign LOCKED = ~RST;
endmodule

module BUFG (output logic O, input logic I);
    assign O = I;
endmodule
/* verilator lint_on BLKSEQ */
`endif
// The supplied data/jtag_bus.sv (read-only, parsed after rtl/*.sv) leaves its tdo and cmd_s[45] unused by design.
/* verilator lint_off UNUSEDSIGNAL */
