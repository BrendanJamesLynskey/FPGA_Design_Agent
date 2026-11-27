// Simulation-only stand-ins for Xilinx primitives (Vivado supplies the real ones in synthesis).
`ifndef SYNTHESIS
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off DECLFILENAME */
/* verilator lint_off PINMISSING */
/* verilator lint_off MULTITOP */

module USR_ACCESSE2 (output logic [31:0] DATA, output logic CFGCLK, output logic DATAVALID);
    assign DATA = 32'h0;
    assign CFGCLK = 1'b0;
    assign DATAVALID = 1'b1;
endmodule

module BUFG (input logic I, output logic O);
    assign O = I;
endmodule

module MMCME4_BASE #(parameter real CLKFBOUT_MULT_F = 10.0, parameter real CLKIN1_PERIOD = 40.0,
                     parameter int DIVCLK_DIVIDE = 1, parameter real CLKOUT0_DIVIDE_F = 10.0) (
    input  logic CLKIN1, CLKFBIN, PWRDWN, RST,
    output logic CLKOUT0, CLKOUT0B, CLKOUT1, CLKOUT1B, CLKOUT2, CLKOUT2B, CLKOUT3, CLKOUT3B,
                 CLKOUT4, CLKOUT5, CLKOUT6, CLKFBOUT, CLKFBOUTB, LOCKED
);
    assign CLKOUT0 = CLKIN1;
    assign {CLKOUT0B, CLKOUT1, CLKOUT1B, CLKOUT2, CLKOUT2B, CLKOUT3, CLKOUT3B, CLKOUT4, CLKOUT5, CLKOUT6} = '0;
    assign CLKFBOUT = CLKIN1;
    assign CLKFBOUTB = 1'b0;
    assign LOCKED = 1'b1;
endmodule

module xpm_cdc_single #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                        parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1) (
    input  logic src_clk, src_in, dest_clk,
    output logic dest_out
);
    logic [DEST_SYNC_FF-1:0] sr = '0;
    always_ff @(posedge dest_clk) sr <= {sr[DEST_SYNC_FF-2:0], src_in};
    assign dest_out = sr[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_array_single #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                              parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1,
                              parameter int WIDTH = 2) (
    input  logic src_clk, dest_clk,
    input  logic [WIDTH-1:0] src_in,
    output logic [WIDTH-1:0] dest_out
);
    logic [WIDTH-1:0] sr [DEST_SYNC_FF];
    always_ff @(posedge dest_clk) begin
        sr[0] <= src_in;
        for (int i = 1; i < DEST_SYNC_FF; i++) sr[i] <= sr[i-1];
    end
    assign dest_out = sr[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_async_rst #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                           parameter int RST_ACTIVE_HIGH = 0) (
    input  logic dest_clk, src_arst,
    output logic dest_arst
);
    logic [DEST_SYNC_FF-1:0] sr;
    always_ff @(posedge dest_clk or posedge src_arst) begin
        if (src_arst) sr <= '1;
        else          sr <= {sr[DEST_SYNC_FF-2:0], 1'b0};
    end
    assign dest_arst = sr[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_pulse #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0, parameter int REG_OUTPUT = 0,
                       parameter int RST_USED = 1, parameter int SIM_ASSERT_CHK = 0) (
    input  logic src_clk, src_pulse, src_rst, dest_clk, dest_rst,
    output logic dest_pulse
);
    logic tgl = 1'b0;
    logic [2:0] sr = '0;
    always_ff @(posedge src_clk) if (src_pulse) tgl <= ~tgl;
    always_ff @(posedge dest_clk) sr <= {sr[1:0], tgl};
    assign dest_pulse = sr[2] ^ sr[1];
endmodule

module xpm_cdc_handshake #(parameter int DEST_EXT_HSK = 1, parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                           parameter int SIM_ASSERT_CHK = 0, parameter int SRC_SYNC_FF = 4, parameter int WIDTH = 1) (
    input  logic src_clk, src_send, dest_clk, dest_ack,
    input  logic [WIDTH-1:0] src_in,
    output logic src_rcv, dest_req,
    output logic [WIDTH-1:0] dest_out
);
    logic [WIDTH-1:0] d = '0;
    logic req_t = 1'b0, ack_t = 1'b0, sending = 1'b0;
    logic [1:0] req_s = '0, ack_s = '0;
    logic req_q = 1'b0;
    initial begin src_rcv = 1'b0; dest_req = 1'b0; dest_out = '0; end
    always_ff @(posedge src_clk) begin
        ack_s <= {ack_s[0], ack_t};
        if (!sending && src_send && !src_rcv) begin d <= src_in; req_t <= ~req_t; sending <= 1'b1; end
        if (sending && ack_s[1] == req_t) begin src_rcv <= 1'b1; sending <= 1'b0; end
        if (!src_send) src_rcv <= 1'b0;
    end
    always_ff @(posedge dest_clk) begin
        req_s <= {req_s[0], req_t};
        req_q <= req_s[1];
        dest_req <= 1'b0;
        if (req_s[1] != req_q) begin dest_out <= d; dest_req <= 1'b1; ack_t <= req_s[1]; end
    end
endmodule

module xpm_fifo_async #(
    parameter int CDC_SYNC_STAGES = 2, parameter DOUT_RESET_VALUE = "0", parameter ECC_MODE = "no_ecc",
    parameter FIFO_MEMORY_TYPE = "auto", parameter int FIFO_READ_LATENCY = 1, parameter int FIFO_WRITE_DEPTH = 2048,
    parameter int FULL_RESET_VALUE = 0, parameter int PROG_EMPTY_THRESH = 10, parameter int PROG_FULL_THRESH = 10,
    parameter int RD_DATA_COUNT_WIDTH = 1, parameter int READ_DATA_WIDTH = 32, parameter READ_MODE = "std",
    parameter int RELATED_CLOCKS = 0, parameter int SIM_ASSERT_CHK = 0, parameter USE_ADV_FEATURES = "0707",
    parameter int WAKEUP_TIME = 0, parameter int WRITE_DATA_WIDTH = 32, parameter int WR_DATA_COUNT_WIDTH = 1
) (
    input  logic rst, wr_clk, wr_en, rd_clk, rd_en, sleep, injectsbiterr, injectdbiterr,
    input  logic [WRITE_DATA_WIDTH-1:0] din,
    output logic [READ_DATA_WIDTH-1:0] dout,
    output logic full, empty, wr_rst_busy, rd_rst_busy, almost_empty, almost_full, data_valid, overflow, underflow,
                 prog_empty, prog_full, sbiterr, dbiterr, wr_ack,
    output logic [WR_DATA_COUNT_WIDTH-1:0] wr_data_count,
    output logic [RD_DATA_COUNT_WIDTH-1:0] rd_data_count
);
    localparam int PW = $clog2(FIFO_WRITE_DEPTH) + 1;
    logic [WRITE_DATA_WIDTH-1:0] mem [FIFO_WRITE_DEPTH];
    logic [PW-1:0] wptr = '0, rptr = '0;
    logic [PW-1:0] wptr_s1 = '0, wptr_s2 = '0, rptr_s1 = '0, rptr_s2 = '0;
    logic [2:0] wbusy = '0, rbusy = '0;
    logic rst_s1 = 1'b0, rst_s2 = 1'b0;
    logic [PW-1:0] wcnt, rcnt;
    always_ff @(posedge wr_clk) begin
        wbusy <= {wbusy[1:0], rst};
        rptr_s1 <= rptr; rptr_s2 <= rptr_s1;
        if (rst) wptr <= '0;
        else if (wr_en && !full && !wr_rst_busy) begin
            mem[wptr[PW-2:0]] <= din;
            wptr <= wptr + 1'b1;
        end
    end
    always_ff @(posedge rd_clk) begin
        rst_s1 <= rst; rst_s2 <= rst_s1;
        rbusy <= {rbusy[1:0], rst_s2};
        wptr_s1 <= wptr; wptr_s2 <= wptr_s1;
        if (rst_s2) rptr <= '0;
        else if (rd_en && !empty && !rd_rst_busy) rptr <= rptr + 1'b1;
    end
    assign wcnt = wptr - rptr_s2;
    assign rcnt = wptr_s2 - rptr;
    assign wr_rst_busy = rst | (|wbusy);
    assign rd_rst_busy = rst_s2 | (|rbusy);
    assign full = (wcnt >= PW'(FIFO_WRITE_DEPTH));
    assign empty = (rcnt == '0);
    assign dout = mem[rptr[PW-2:0]];
    assign wr_data_count = wcnt[WR_DATA_COUNT_WIDTH-1:0];
    assign rd_data_count = rcnt[RD_DATA_COUNT_WIDTH-1:0];
    assign {almost_empty, almost_full, data_valid, overflow, underflow, prog_empty, prog_full, sbiterr, dbiterr, wr_ack} = '0;
endmodule
/* verilator lint_on UNUSEDSIGNAL */
`endif
