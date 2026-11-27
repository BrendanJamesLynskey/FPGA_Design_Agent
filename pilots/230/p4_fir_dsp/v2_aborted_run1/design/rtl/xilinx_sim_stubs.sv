// Simulation-only stand-ins for Xilinx primitives. Vivado supplies the real ones (SYNTHESIS is defined there).
`ifndef SYNTHESIS
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off DECLFILENAME */
/* verilator lint_off MULTITOP */
/* verilator lint_off WIDTHEXPAND */
/* verilator lint_off WIDTHTRUNC */
/* verilator lint_off PINCONNECTEMPTY */
/* verilator lint_off UNDRIVEN */
/* verilator lint_off BLKSEQ */
/* verilator lint_off SYNCASYNCNET */

module xpm_cdc_single #(
    parameter integer DEST_SYNC_FF = 4,
    parameter integer INIT_SYNC_FF = 0,
    parameter integer SIM_ASSERT_CHK = 0,
    parameter integer SRC_INPUT_REG = 1
) (
    input  logic src_clk,
    input  logic src_in,
    input  logic dest_clk,
    output logic dest_out
);
    logic a = 1'b0;
    logic b = 1'b0;
    always_ff @(posedge dest_clk) begin
        a <= src_in;
        b <= a;
    end
    assign dest_out = b;
endmodule

module xpm_cdc_array_single #(
    parameter integer DEST_SYNC_FF = 4,
    parameter integer INIT_SYNC_FF = 0,
    parameter integer SIM_ASSERT_CHK = 0,
    parameter integer SRC_INPUT_REG = 1,
    parameter integer WIDTH = 2
) (
    input  logic             src_clk,
    input  logic [WIDTH-1:0] src_in,
    input  logic             dest_clk,
    output logic [WIDTH-1:0] dest_out
);
    logic [WIDTH-1:0] a = '0;
    logic [WIDTH-1:0] b = '0;
    always_ff @(posedge dest_clk) begin
        a <= src_in;
        b <= a;
    end
    assign dest_out = b;
endmodule

module xpm_cdc_gray #(
    parameter integer DEST_SYNC_FF = 4,
    parameter integer INIT_SYNC_FF = 0,
    parameter integer REG_OUTPUT = 0,
    parameter integer SIM_ASSERT_CHK = 0,
    parameter integer SIM_LOSSLESS_GRAY_CHK = 0,
    parameter integer WIDTH = 2
) (
    input  logic             src_clk,
    input  logic [WIDTH-1:0] src_in_bin,
    input  logic             dest_clk,
    output logic [WIDTH-1:0] dest_out_bin
);
    logic [WIDTH-1:0] g;
    logic [WIDTH-1:0] a = '0;
    logic [WIDTH-1:0] b = '0;
    logic [WIDTH-1:0] bin;
    always_comb g = src_in_bin ^ (src_in_bin >> 1);
    always_ff @(posedge dest_clk) begin
        a <= g;
        b <= a;
    end
    always_comb begin
        bin[WIDTH-1] = b[WIDTH-1];
        for (int i = WIDTH-2; i >= 0; i--) bin[i] = bin[i+1] ^ b[i];
    end
    assign dest_out_bin = bin;
endmodule

module xpm_cdc_handshake #(
    parameter integer DEST_EXT_HSK = 1,
    parameter integer DEST_SYNC_FF = 4,
    parameter integer INIT_SYNC_FF = 0,
    parameter integer SIM_ASSERT_CHK = 0,
    parameter integer SRC_SYNC_FF = 4,
    parameter integer WIDTH = 1
) (
    input  logic             src_clk,
    input  logic [WIDTH-1:0] src_in,
    input  logic             src_send,
    output logic             src_rcv,
    input  logic             dest_clk,
    output logic [WIDTH-1:0] dest_out,
    output logic             dest_req,
    input  logic             dest_ack
);
    logic d1 = 1'b0, d2 = 1'b0, a1 = 1'b0, a2 = 1'b0;
    always_ff @(posedge dest_clk) begin
        d1 <= src_send;
        d2 <= d1;
    end
    assign dest_req = d2;
    assign dest_out = src_in;
    assign src_rcv  = dest_ack;
endmodule

module xpm_cdc_pulse #(
    parameter integer DEST_SYNC_FF = 4,
    parameter integer INIT_SYNC_FF = 0,
    parameter integer REG_OUTPUT = 0,
    parameter integer RST_USED = 1,
    parameter integer SIM_ASSERT_CHK = 0
) (
    output logic dest_pulse,
    input  logic dest_clk,
    input  logic dest_rst,
    input  logic src_clk,
    input  logic src_pulse,
    input  logic src_rst
);
    logic       tog = 1'b0;
    logic [3:0] s = 4'd0;
    logic       q = 1'b0;
    always_ff @(posedge src_clk) if (src_pulse) tog <= ~tog;
    always_ff @(posedge dest_clk) begin
        s <= {s[2:0], tog};
        q <= s[DEST_SYNC_FF-1];
    end
    assign dest_pulse = s[DEST_SYNC_FF-1] ^ q;
endmodule

module xpm_cdc_async_rst #(
    parameter integer DEST_SYNC_FF = 4,
    parameter integer INIT_SYNC_FF = 0,
    parameter integer RST_ACTIVE_HIGH = 0
) (
    output logic dest_arst,
    input  logic dest_clk,
    input  logic src_arst
);
    logic [DEST_SYNC_FF-1:0] sr = '1;
    always_ff @(posedge dest_clk or posedge src_arst) begin
        if (src_arst) sr <= '1;
        else          sr <= {sr[DEST_SYNC_FF-2:0], 1'b0};
    end
    assign dest_arst = sr[DEST_SYNC_FF-1];
endmodule

module xpm_fifo_async #(
    parameter integer CDC_SYNC_STAGES = 2,
    parameter         DOUT_RESET_VALUE = "0",
    parameter         ECC_MODE = "no_ecc",
    parameter         FIFO_MEMORY_TYPE = "auto",
    parameter integer FIFO_READ_LATENCY = 1,
    parameter integer FIFO_WRITE_DEPTH = 2048,
    parameter integer FULL_RESET_VALUE = 0,
    parameter integer PROG_EMPTY_THRESH = 10,
    parameter integer PROG_FULL_THRESH = 10,
    parameter integer RD_DATA_COUNT_WIDTH = 1,
    parameter integer READ_DATA_WIDTH = 32,
    parameter         READ_MODE = "std",
    parameter integer RELATED_CLOCKS = 0,
    parameter integer SIM_ASSERT_CHK = 0,
    parameter         USE_ADV_FEATURES = "0707",
    parameter integer WAKEUP_TIME = 0,
    parameter integer WRITE_DATA_WIDTH = 32,
    parameter integer WR_DATA_COUNT_WIDTH = 1
) (
    output logic                           almost_empty,
    output logic                           almost_full,
    output logic                           data_valid,
    output logic                           dbiterr,
    output logic [READ_DATA_WIDTH-1:0]     dout,
    output logic                           empty,
    output logic                           full,
    output logic                           overflow,
    output logic                           prog_empty,
    output logic                           prog_full,
    output logic [RD_DATA_COUNT_WIDTH-1:0] rd_data_count,
    output logic                           rd_rst_busy,
    output logic                           sbiterr,
    output logic                           underflow,
    output logic                           wr_ack,
    output logic [WR_DATA_COUNT_WIDTH-1:0] wr_data_count,
    output logic                           wr_rst_busy,
    input  logic [WRITE_DATA_WIDTH-1:0]    din,
    input  logic                           injectdbiterr,
    input  logic                           injectsbiterr,
    input  logic                           rd_clk,
    input  logic                           rd_en,
    input  logic                           rst,
    input  logic                           sleep,
    input  logic                           wr_clk,
    input  logic                           wr_en
);
    localparam integer AW = $clog2(FIFO_WRITE_DEPTH);
    logic [WRITE_DATA_WIDTH-1:0] mem [0:FIFO_WRITE_DEPTH-1];
    logic [AW:0] wptr = '0, rptr = '0;
    logic [AW:0] wptr_r1 = '0, wptr_r2 = '0, rptr_w1 = '0, rptr_w2 = '0;
    logic [2:0]  wbusy = 3'd0, rbusy = 3'd0;
    logic        rst_r1 = 1'b0, rst_r2 = 1'b0;
    logic [AW:0] wdiff, rdiff;
    logic [WR_DATA_COUNT_WIDTH-1:0] wcnt = '0;
    logic [RD_DATA_COUNT_WIDTH-1:0] rcnt = '0;

    assign wdiff = wptr - rptr_w2;
    assign rdiff = wptr_r2 - rptr;
    assign wr_rst_busy = rst | (wbusy != 3'd0);
    assign rd_rst_busy = rst_r2 | (rbusy != 3'd0);
    assign full  = wdiff[AW];
    assign empty = rd_rst_busy | (wptr_r2 == rptr);
    assign dout  = mem[rptr[AW-1:0]];

    always_ff @(posedge wr_clk) begin
        rptr_w1 <= rptr;
        rptr_w2 <= rptr_w1;
        if (rst) begin
            wptr  <= '0;
            wbusy <= 3'd4;
            wcnt  <= '0;
        end else begin
            if (wbusy != 3'd0) wbusy <= wbusy - 3'd1;
            else if (wr_en && !full) begin
                mem[wptr[AW-1:0]] <= din;
                wptr <= wptr + 1'b1;
            end
            wcnt <= wdiff;
        end
    end

    always_ff @(posedge rd_clk) begin
        rst_r1  <= rst;
        rst_r2  <= rst_r1;
        wptr_r1 <= wptr;
        wptr_r2 <= wptr_r1;
        if (rst_r2) begin
            rptr    <= '0;
            rbusy   <= 3'd4;
            wptr_r1 <= '0;
            wptr_r2 <= '0;
            rcnt    <= '0;
        end else begin
            if (rbusy != 3'd0) rbusy <= rbusy - 3'd1;
            else if (rd_en && !empty) rptr <= rptr + 1'b1;
            rcnt <= rdiff;
        end
    end

    assign wr_data_count = wcnt;
    assign rd_data_count = rcnt;
    assign almost_empty = 1'b0;
    assign almost_full  = 1'b0;
    assign data_valid   = !empty;
    assign dbiterr      = 1'b0;
    assign sbiterr      = 1'b0;
    assign overflow     = 1'b0;
    assign underflow    = 1'b0;
    assign prog_empty   = 1'b0;
    assign prog_full    = 1'b0;
    assign wr_ack       = 1'b0;
endmodule

module USR_ACCESSE2 (
    output logic        CFGCLK,
    output logic [31:0] DATA,
    output logic        DATAVALID
);
    assign CFGCLK = 1'b0;
    assign DATA = 32'd0;
    assign DATAVALID = 1'b1;
endmodule

module BUFG (
    output logic O,
    input  logic I
);
    assign O = I;
endmodule

module MMCME4_BASE #(
    parameter real BANDWIDTH = 0.0,
    parameter real CLKFBOUT_MULT_F = 5.0,
    parameter real CLKFBOUT_PHASE = 0.0,
    parameter real CLKIN1_PERIOD = 0.0,
    parameter real CLKOUT0_DIVIDE_F = 1.0,
    parameter real CLKOUT0_DUTY_CYCLE = 0.5,
    parameter real CLKOUT0_PHASE = 0.0,
    parameter integer DIVCLK_DIVIDE = 1,
    parameter real REF_JITTER1 = 0.0,
    parameter integer STARTUP_WAIT = 0
) (
    output logic CLKFBOUT,
    output logic CLKFBOUTB,
    output logic CLKOUT0,
    output logic CLKOUT0B,
    output logic LOCKED,
    input  logic CLKFBIN,
    input  logic CLKIN1,
    input  logic PWRDWN,
    input  logic RST
);
    assign CLKFBOUT = CLKIN1;
    assign CLKFBOUTB = 1'b0;
    assign CLKOUT0 = CLKIN1;
    assign CLKOUT0B = 1'b0;
    assign LOCKED = 1'b1;
endmodule
`endif
