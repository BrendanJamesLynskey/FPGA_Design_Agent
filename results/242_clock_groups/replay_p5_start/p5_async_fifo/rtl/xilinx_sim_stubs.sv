// Simulation-only stand-ins for Xilinx primitives; Vivado supplies the real ones in synthesis.
`ifndef SYNTHESIS
/* verilator lint_off DECLFILENAME */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off PROCASSINIT */
/* verilator lint_off SYNCASYNCNET */
/* verilator lint_off MULTITOP */

module xpm_cdc_single #(
    parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0,
    parameter integer SIM_ASSERT_CHK = 0, parameter integer SRC_INPUT_REG = 1, parameter integer VERSION = 0
) (
    input  logic src_clk, input logic src_in, input logic dest_clk, output logic dest_out
);
    logic [DEST_SYNC_FF-1:0] sr = '0;
    wire unused_clk = src_clk;
    always_ff @(posedge dest_clk) sr <= {sr[DEST_SYNC_FF-2:0], src_in};
    assign dest_out = sr[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_array_single #(
    parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0,
    parameter integer SIM_ASSERT_CHK = 0, parameter integer SRC_INPUT_REG = 1,
    parameter integer VERSION = 0, parameter integer WIDTH = 2
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in, input logic dest_clk, output logic [WIDTH-1:0] dest_out
);
    logic [WIDTH-1:0] s0 = '0;
    logic [WIDTH-1:0] sr [DEST_SYNC_FF];
    initial for (int i = 0; i < DEST_SYNC_FF; i++) sr[i] = '0;
    always_ff @(posedge src_clk) s0 <= src_in;
    wire [WIDTH-1:0] d = (SRC_INPUT_REG != 0) ? s0 : src_in;
    always_ff @(posedge dest_clk) begin
        sr[0] <= d;
        for (int i = 1; i < DEST_SYNC_FF; i++) sr[i] <= sr[i-1];
    end
    assign dest_out = sr[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_async_rst #(
    parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0,
    parameter integer RST_ACTIVE_HIGH = 0, parameter integer VERSION = 0
) (
    input logic src_arst, input logic dest_clk, output logic dest_arst
);
    logic [DEST_SYNC_FF-1:0] sr = '1;
    wire a = (RST_ACTIVE_HIGH != 0) ? src_arst : ~src_arst;
    always_ff @(posedge dest_clk) begin
        if (a) sr <= '1;
        else   sr <= {sr[DEST_SYNC_FF-2:0], 1'b0};
    end
    // assertion is passed through combinationally (asynchronous assert), release is synchronous
    wire q = sr[DEST_SYNC_FF-1] | a;
    assign dest_arst = (RST_ACTIVE_HIGH != 0) ? q : ~q;
endmodule

module xpm_cdc_handshake #(
    parameter integer DEST_EXT_HSK = 1, parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0,
    parameter integer SIM_ASSERT_CHK = 0, parameter integer SRC_SYNC_FF = 4,
    parameter integer VERSION = 0, parameter integer WIDTH = 1
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in, input logic src_send, output logic src_rcv,
    input  logic dest_clk, output logic [WIDTH-1:0] dest_out, output logic dest_req, input logic dest_ack
);
    logic [WIDTH-1:0] data_l = '0;
    logic req_t = 1'b0, ack_t = 1'b0, sent = 1'b0, rcv = 1'b0;
    logic a1 = 1'b0, a2 = 1'b0, r1 = 1'b0, r2 = 1'b0, prev = 1'b0, rq = 1'b0;
    logic [WIDTH-1:0] dout = '0;
    always_ff @(posedge src_clk) begin
        a1 <= ack_t; a2 <= a1;
        if (src_send && !sent && !rcv) begin data_l <= src_in; req_t <= ~req_t; sent <= 1'b1; end
        if (sent && (a2 == req_t)) begin rcv <= 1'b1; sent <= 1'b0; end
        if (!src_send) rcv <= 1'b0;
    end
    always_ff @(posedge dest_clk) begin
        r1 <= req_t; r2 <= r1; prev <= r2;
        rq <= 1'b0;
        if (r2 != prev) begin rq <= 1'b1; dout <= data_l; ack_t <= r2; end
    end
    assign src_rcv = rcv;
    assign dest_req = rq;
    assign dest_out = dout;
    wire unused_ack = dest_ack;
endmodule

module xpm_fifo_async #(
    parameter integer CDC_SYNC_STAGES = 2, parameter DOUT_RESET_VALUE = "0", parameter ECC_MODE = "no_ecc",
    parameter FIFO_MEMORY_TYPE = "auto", parameter integer FIFO_READ_LATENCY = 0,
    parameter integer FIFO_WRITE_DEPTH = 2048, parameter integer FULL_RESET_VALUE = 0,
    parameter integer PROG_EMPTY_THRESH = 10, parameter integer PROG_FULL_THRESH = 10,
    parameter integer RD_DATA_COUNT_WIDTH = 1, parameter integer READ_DATA_WIDTH = 32,
    parameter READ_MODE = "std", parameter integer RELATED_CLOCKS = 0, parameter integer SIM_ASSERT_CHK = 0,
    parameter USE_ADV_FEATURES = "0707", parameter integer WAKEUP_TIME = 0,
    parameter integer WRITE_DATA_WIDTH = 32, parameter integer WR_DATA_COUNT_WIDTH = 1
) (
    input  logic rst, input logic sleep,
    input  logic wr_clk, input logic wr_en, input logic [WRITE_DATA_WIDTH-1:0] din,
    output logic full, output logic [WR_DATA_COUNT_WIDTH-1:0] wr_data_count, output logic wr_rst_busy,
    input  logic rd_clk, input logic rd_en, output logic [READ_DATA_WIDTH-1:0] dout,
    output logic empty, output logic rd_rst_busy,
    output logic overflow, output logic underflow,
    input  logic injectsbiterr, input logic injectdbiterr
);
    localparam integer AW = $clog2(FIFO_WRITE_DEPTH);
    logic [WRITE_DATA_WIDTH-1:0] mem [FIFO_WRITE_DEPTH];
    logic [AW:0] wptr = '0, rptr = '0, wptr_r1 = '0, wptr_r2 = '0, rptr_w1 = '0, rptr_w2 = '0;
    logic [7:0] wbusy = '0;
    logic [3:0] rbusy = '0;
    logic rs1 = 1'b0, rs2 = 1'b0;
    wire wr_busy = rst | (|wbusy);
    wire rd_busy = rs2 | (|rbusy);
    always_ff @(posedge wr_clk) begin
        wbusy <= {wbusy[6:0], rst};
        rptr_w1 <= rptr; rptr_w2 <= rptr_w1;
        if (rst) wptr <= '0;
        else if (wr_en && !full && !wr_busy) begin
            mem[wptr[AW-1:0]] <= din;
            wptr <= wptr + 1'b1;
        end
    end
    always_ff @(posedge rd_clk) begin
        rs1 <= rst; rs2 <= rs1;
        rbusy <= {rbusy[2:0], rs2};
        wptr_r1 <= wptr; wptr_r2 <= wptr_r1;
        if (rs2) rptr <= '0;
        else if (rd_en && !empty) rptr <= rptr + 1'b1;
    end
    wire [AW:0] occ = wptr - rptr_w2;
    assign full = occ[AW];
    assign wr_data_count = occ;
    assign overflow = wr_en & full & ~wr_busy;
    assign underflow = rd_en & empty;
    assign wr_rst_busy = wr_busy;
    assign rd_rst_busy = rd_busy;
    assign empty = (wptr_r2 == rptr) | rd_busy;
    assign dout = mem[rptr[AW-1:0]];
    wire unused = &{1'b0, sleep, injectsbiterr, injectdbiterr};
endmodule

module IBUFDS_GTE4 #(
    parameter [0:0] REFCLK_EN_TX_PATH = 1'b0, parameter [1:0] REFCLK_HROW_CK_SEL = 2'b00,
    parameter [1:0] REFCLK_ICNTL_RX = 2'b00
) (
    input logic I, input logic IB, input logic CEB, output logic O, output logic ODIV2
);
    assign O = I;
    assign ODIV2 = I;
    wire unused = &{1'b0, IB, CEB};
endmodule

module BUFG_GT #(parameter [2:0] STARTUP_RATE = 3'b0) (
    input logic CE, input logic CEMASK, input logic CLR, input logic CLRMASK, input logic [2:0] DIV,
    input logic I, output logic O
);
    assign O = I;
    wire unused = &{1'b0, CE, CEMASK, CLR, CLRMASK, DIV};
endmodule

module USR_ACCESSE2 (output logic CFGCLK, output logic [31:0] DATA, output logic DATAVALID);
    assign CFGCLK = 1'b0;
    assign DATA = 32'h0;
    assign DATAVALID = 1'b1;
endmodule

`endif
