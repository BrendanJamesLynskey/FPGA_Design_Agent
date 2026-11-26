// Simulation-only stand-ins for Xilinx primitives and XPM macros. Vivado supplies the real ones (SYNTHESIS is defined).
`ifndef SYNTHESIS
/* verilator lint_off DECLFILENAME */
/* verilator lint_off PROCASSINIT */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off PINMISSING */

module IBUFDS_GTE4 (input logic I, input logic IB, input logic CEB, output logic O, output logic ODIV2);
    assign O     = I & ~IB & ~CEB;
    assign ODIV2 = I & ~IB & ~CEB;
endmodule

module BUFG_GT (input logic I, input logic CE, input logic CEMASK, input logic CLR, input logic CLRMASK,
                input logic [2:0] DIV, output logic O);
    assign O = I & CE & ~CLR & ~CEMASK & ~CLRMASK & ~(|DIV);
endmodule

module USR_ACCESSE2 (output logic CFGCLK, output logic [31:0] DATA, output logic DATAVALID);
    assign CFGCLK    = 1'b0;
    assign DATA      = 32'h0;
    assign DATAVALID = 1'b1;
endmodule

module xpm_cdc_single #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                        parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1) (
    /* verilator lint_off UNUSEDSIGNAL */
    input logic src_clk,

    input logic src_in, input logic dest_clk, output logic dest_out);
    logic [DEST_SYNC_FF-1:0] sr = '0;
    always_ff @(posedge dest_clk) sr <= {sr[DEST_SYNC_FF-2:0], src_in};
    assign dest_out = sr[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_array_single #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                              parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1,
                              parameter int WIDTH = 2) (
    input logic src_clk, input logic [WIDTH-1:0] src_in, input logic dest_clk, output logic [WIDTH-1:0] dest_out);
    logic [WIDTH-1:0] sr [DEST_SYNC_FF];
    logic [WIDTH-1:0] sq = '0;
    initial for (int i = 0; i < DEST_SYNC_FF; i++) sr[i] = '0;
    always_ff @(posedge src_clk) sq <= src_in;
    always_ff @(posedge dest_clk) begin
        sr[0] <= (SRC_INPUT_REG != 0) ? sq : src_in;
        for (int i = 1; i < DEST_SYNC_FF; i++) sr[i] <= sr[i-1];
    end
    assign dest_out = sr[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_pulse #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0, parameter int REG_OUTPUT = 0,
                       parameter int RST_USED = 1, parameter int SIM_ASSERT_CHK = 0) (
    input logic src_clk, input logic src_pulse, input logic src_rst,
    input logic dest_clk, input logic dest_rst, output logic dest_pulse);
    logic       t = 1'b0;
    logic [2:0] s = '0;
    always_ff @(posedge src_clk) begin
        if (src_rst) t <= 1'b0;
        else if (src_pulse) t <= ~t;
    end
    always_ff @(posedge dest_clk) begin
        if (dest_rst) s <= '0;
        else s <= {s[1:0], t};
    end
    assign dest_pulse = s[2] ^ s[1];
endmodule

module xpm_cdc_handshake #(parameter int DEST_EXT_HSK = 1, parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                           parameter int SIM_ASSERT_CHK = 0, parameter int SRC_SYNC_FF = 4, parameter int WIDTH = 1) (
    input logic src_clk, input logic [WIDTH-1:0] src_in, input logic src_send, output logic src_rcv,
    input logic dest_clk, input logic dest_ack, output logic dest_req, output logic [WIDTH-1:0] dest_out);
    logic req_t = 1'b0, ack_t = 1'b0, busy = 1'b0;
    logic [WIDTH-1:0] data_q = '0;
    logic [1:0] ack_s = '0;
    logic [2:0] req_s = '0;
    initial begin src_rcv = 1'b0; dest_req = 1'b0; dest_out = '0; end
    always_ff @(posedge src_clk) begin
        ack_s <= {ack_s[0], ack_t};
        if (src_send && !busy && !src_rcv) begin
            busy <= 1'b1; req_t <= ~req_t; data_q <= src_in;
        end else if (busy && ack_s[1] == req_t) begin
            busy <= 1'b0; src_rcv <= 1'b1;
        end else if (src_rcv && !src_send) begin
            src_rcv <= 1'b0;
        end
    end
    always_ff @(posedge dest_clk) begin
        req_s    <= {req_s[1:0], req_t};
        dest_req <= 1'b0;
        if (req_s[1] != req_s[2]) begin
            dest_out <= data_q; dest_req <= 1'b1; ack_t <= req_s[1];
        end
    end
endmodule

module xpm_cdc_async_rst #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                           parameter int RST_ACTIVE_HIGH = 1) (
    input logic dest_clk, input logic src_arst, output logic dest_arst);
    logic [DEST_SYNC_FF-1:0] r = '1;
    always_ff @(posedge dest_clk) r <= {r[DEST_SYNC_FF-2:0], src_arst};
    assign dest_arst = r[DEST_SYNC_FF-1];
endmodule

module xpm_fifo_async #(
    parameter int CDC_SYNC_STAGES = 2, parameter int DOUT_RESET_VALUE = 0, parameter string ECC_MODE = "no_ecc",
    parameter string FIFO_MEMORY_TYPE = "block", parameter int FIFO_READ_LATENCY = 1,
    parameter int FIFO_WRITE_DEPTH = 2048, parameter int FULL_RESET_VALUE = 0, parameter int PROG_EMPTY_THRESH = 10,
    parameter int PROG_FULL_THRESH = 10, parameter int RD_DATA_COUNT_WIDTH = 1, parameter int READ_DATA_WIDTH = 32,
    parameter string READ_MODE = "std", parameter int RELATED_CLOCKS = 0, parameter int SIM_ASSERT_CHK = 0,
    parameter string USE_ADV_FEATURES = "0707", parameter int WAKEUP_TIME = 0, parameter int WRITE_DATA_WIDTH = 32,
    parameter int WR_DATA_COUNT_WIDTH = 1
) (
    input  logic                        sleep,
    input  logic                        rst,
    input  logic                        wr_clk,
    input  logic                        wr_en,
    input  logic [WRITE_DATA_WIDTH-1:0] din,
    output logic                        full,
    output logic                        overflow,
    output logic [WR_DATA_COUNT_WIDTH-1:0] wr_data_count,
    output logic                        wr_rst_busy,
    input  logic                        rd_clk,
    input  logic                        rd_en,
    output logic [READ_DATA_WIDTH-1:0]  dout,
    output logic                        empty,
    output logic                        underflow,
    output logic                        rd_rst_busy,
    input  logic                        injectsbiterr,
    input  logic                        injectdbiterr
);
    localparam int AW = $clog2(FIFO_WRITE_DEPTH);
    logic [WRITE_DATA_WIDTH-1:0] mem [FIFO_WRITE_DEPTH];
    logic [AW:0] wptr = '0, rptr = '0, wg, rg;
    logic [AW:0] rg_s1 = '0, rg_s2 = '0, wg_s1 = '0, wg_s2 = '0;
    logic [3:0]  wbc = 4'd8, rbc = 4'd8;
    logic        rs1 = 1'b1, rs2 = 1'b1;
    initial begin overflow = 1'b0; underflow = 1'b0; dout = '0; end

    logic [AW:0] rbin_w;
    always_comb begin
        logic [AW:0] acc;
        acc = '0;
        for (int i = 0; i <= AW; i++) acc = acc ^ (rg_s2 >> i);
        rbin_w = acc;
    end
    assign wr_data_count = WR_DATA_COUNT_WIDTH'(wptr - rbin_w);
    assign wg = wptr ^ (wptr >> 1);
    assign rg = rptr ^ (rptr >> 1);
    assign wr_rst_busy = rst || (wbc != 4'd0);
    assign rd_rst_busy = rs2 || (rbc != 4'd0);
    assign full  = (wg == {~rg_s2[AW:AW-1], rg_s2[AW-2:0]});
    assign empty = (rg == wg_s2);

    always_ff @(posedge wr_clk) begin
        rg_s1 <= rg; rg_s2 <= rg_s1;
        if (rst) begin
            wptr <= '0; wbc <= 4'd8; overflow <= 1'b0;
        end else begin
            if (wbc != 4'd0) wbc <= wbc - 4'd1;
            overflow <= wr_en && (full || wr_rst_busy);
            if (wr_en && !full && !wr_rst_busy) begin
                mem[wptr[AW-1:0]] <= din;
                wptr <= wptr + 1'b1;
            end
        end
    end

    always_ff @(posedge rd_clk) begin
        rs1 <= rst; rs2 <= rs1;
        wg_s1 <= wg; wg_s2 <= wg_s1;
        if (rs2) begin
            rptr <= '0; rbc <= 4'd8; underflow <= 1'b0;
        end else begin
            if (rbc != 4'd0) rbc <= rbc - 4'd1;
            underflow <= rd_en && (empty || rd_rst_busy);
            if (rd_en && !empty && !rd_rst_busy) begin
                dout <= mem[rptr[AW-1:0]];
                rptr <= rptr + 1'b1;
            end
        end
    end
endmodule

`endif
