// Simulation-only stand-ins for Xilinx primitives (Vivado supplies the real ones in synthesis).
`ifndef SYNTHESIS
/* verilator lint_off DECLFILENAME */
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off PINCONNECTEMPTY */

module xpm_cdc_single #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                        parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1) (
    input  logic src_clk, input logic src_in, input logic dest_clk, output logic dest_out);
    logic [DEST_SYNC_FF-1:0] s = '0;
    always_ff @(posedge dest_clk) s <= {s[DEST_SYNC_FF-2:0], src_in};
    assign dest_out = s[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_array_single #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                              parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1,
                              parameter int WIDTH = 2) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in, input logic dest_clk,
    output logic [WIDTH-1:0] dest_out);
    logic [WIDTH-1:0] s [DEST_SYNC_FF];
    always_ff @(posedge dest_clk) begin
        s[0] <= src_in;
        for (int i = 1; i < DEST_SYNC_FF; i++) s[i] <= s[i-1];
    end
    assign dest_out = s[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_pulse #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                       parameter int REG_OUTPUT = 0, parameter int RST_USED = 1,
                       parameter int SIM_ASSERT_CHK = 0) (
    input  logic src_clk, input logic src_rst, input logic src_pulse,
    input  logic dest_clk, input logic dest_rst, output logic dest_pulse);
    logic tog = 1'b0;
    always_ff @(posedge src_clk) if (src_pulse) tog <= ~tog;
    logic [DEST_SYNC_FF:0] s = '0;
    always_ff @(posedge dest_clk) s <= {s[DEST_SYNC_FF-1:0], tog};
    assign dest_pulse = s[DEST_SYNC_FF] ^ s[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_handshake #(parameter int DEST_EXT_HSK = 1, parameter int DEST_SYNC_FF = 4,
                           parameter int INIT_SYNC_FF = 0, parameter int SIM_ASSERT_CHK = 0,
                           parameter int SRC_SYNC_FF = 4, parameter int WIDTH = 1) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in, input logic src_send, output logic src_rcv,
    input  logic dest_clk, input logic dest_ack, output logic dest_req, output logic [WIDTH-1:0] dest_out);
    logic [WIDTH-1:0] data = '0;
    logic             req_s = 1'b0;
    always_ff @(posedge src_clk) begin
        if (src_send && !src_rcv && !req_s) begin data <= src_in; req_s <= 1'b1; end
        else if (!src_send && src_rcv)       req_s <= 1'b0;
    end
    logic [DEST_SYNC_FF-1:0] d = '0;
    logic dq = 1'b0;
    always_ff @(posedge dest_clk) begin d <= {d[DEST_SYNC_FF-2:0], req_s}; dq <= d[DEST_SYNC_FF-1]; end
    assign dest_req = d[DEST_SYNC_FF-1] & ~dq;
    assign dest_out = data;
    logic [SRC_SYNC_FF-1:0] a = '0;
    always_ff @(posedge src_clk) a <= {a[SRC_SYNC_FF-2:0], dq};
    assign src_rcv = a[SRC_SYNC_FF-1];
endmodule

module xpm_cdc_async_rst #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                           parameter int RST_ACTIVE_HIGH = 0) (
    input logic dest_clk, input logic src_arst, output logic dest_arst);
    logic [DEST_SYNC_FF-1:0] s = '1;
    always_ff @(posedge dest_clk or posedge src_arst)
        if (src_arst) s <= '1; else s <= {s[DEST_SYNC_FF-2:0], 1'b0};
    assign dest_arst = s[DEST_SYNC_FF-1];
endmodule

module xpm_fifo_async #(parameter int CDC_SYNC_STAGES = 2, parameter int DOUT_RESET_VALUE = 0,
                        parameter string ECC_MODE = "no_ecc", parameter string FIFO_MEMORY_TYPE = "auto",
                        parameter int FIFO_READ_LATENCY = 0, parameter int FIFO_WRITE_DEPTH = 2048,
                        parameter int FULL_RESET_VALUE = 0, parameter int PROG_EMPTY_THRESH = 10,
                        parameter int PROG_FULL_THRESH = 10, parameter int RD_DATA_COUNT_WIDTH = 1,
                        parameter int READ_DATA_WIDTH = 32, parameter string READ_MODE = "std",
                        parameter int RELATED_CLOCKS = 0, parameter int SIM_ASSERT_CHK = 0,
                        parameter string USE_ADV_FEATURES = "0707", parameter int WAKEUP_TIME = 0,
                        parameter int WRITE_DATA_WIDTH = 32, parameter int WR_DATA_COUNT_WIDTH = 1) (
    input  logic sleep, input logic rst,
    input  logic wr_clk, input logic wr_en, input logic [WRITE_DATA_WIDTH-1:0] din,
    output logic full, output logic wr_rst_busy, output logic [WR_DATA_COUNT_WIDTH-1:0] wr_data_count,
    input  logic rd_clk, input logic rd_en, output logic [READ_DATA_WIDTH-1:0] dout,
    output logic empty, output logic rd_rst_busy, output logic [RD_DATA_COUNT_WIDTH-1:0] rd_data_count,
    input  logic injectsbiterr, input logic injectdbiterr);
    localparam int AW = $clog2(FIFO_WRITE_DEPTH);
    logic [WRITE_DATA_WIDTH-1:0] mem [FIFO_WRITE_DEPTH];
    logic [AW:0] wptr = '0, rptr = '0;
    logic [AW:0] rp_s1 = '0, rp_s2 = '0, wp_s1 = '0, wp_s2 = '0;
    logic        rst_q = 1'b0, rst_tog = 1'b0;
    logic [2:0]  wbusy = '0, rbusy = '0;
    logic        tg1 = 1'b0, tg2 = 1'b0, tg3 = 1'b0;
    always_ff @(posedge wr_clk) begin
        rst_q <= rst;
        if (rst && !rst_q) rst_tog <= ~rst_tog;
        rp_s1 <= rptr; rp_s2 <= rp_s1;
        if (rst) begin wptr <= '0; wbusy <= 3'd3; rp_s1 <= '0; rp_s2 <= '0; end
        else begin
            if (wbusy != 0) wbusy <= wbusy - 3'd1;
            else if (wr_en && !full) begin mem[wptr[AW-1:0]] <= din; wptr <= wptr + 1'b1; end
        end
    end
    wire rd_ev = (tg2 != tg3);
    always_ff @(posedge rd_clk) begin
        tg1 <= rst_tog; tg2 <= tg1; tg3 <= tg2;
        wp_s1 <= wptr; wp_s2 <= wp_s1;
        if (rd_ev) begin rptr <= '0; rbusy <= 3'd2; wp_s1 <= '0; wp_s2 <= '0; end
        else begin
            if (rbusy != 0) rbusy <= rbusy - 3'd1;
            else if (rd_en && !empty) rptr <= rptr + 1'b1;
        end
    end
    assign full          = ((wptr - rp_s2) == (AW+1)'(FIFO_WRITE_DEPTH));
    assign wr_rst_busy   = (wbusy != 0) | rst;
    assign wr_data_count = WR_DATA_COUNT_WIDTH'(wptr - rp_s2);
    assign empty         = (rptr == wp_s2) | (rst_tog != tg3) | (rbusy != 0);
    assign rd_rst_busy   = (rbusy != 0) | rd_ev;
    assign rd_data_count = RD_DATA_COUNT_WIDTH'(wp_s2 - rptr);
    assign dout          = empty ? '0 : mem[rptr[AW-1:0]];
endmodule

module USR_ACCESSE2 (output logic [31:0] DATA, output logic DATAVALID, output logic CFGCLK);
    assign DATA = 32'd0;
    assign DATAVALID = 1'b1;
    assign CFGCLK = 1'b0;
endmodule

module MMCME4_BASE #(parameter real CLKIN1_PERIOD = 10.0, parameter int DIVCLK_DIVIDE = 1,
                     parameter real CLKFBOUT_MULT_F = 5.0, parameter real CLKOUT0_DIVIDE_F = 1.0) (
    input logic CLKIN1, input logic CLKFBIN, input logic RST, input logic PWRDWN,
    output logic CLKOUT0, output logic CLKFBOUT, output logic LOCKED);
    assign CLKOUT0 = 1'b0; assign CLKFBOUT = CLKIN1; assign LOCKED = 1'b1;
endmodule

module BUFG (input logic I, output logic O);
    assign O = I;
endmodule
/* verilator lint_on PINCONNECTEMPTY */
/* verilator lint_on UNUSEDPARAM */
/* verilator lint_on UNUSEDSIGNAL */
/* verilator lint_on DECLFILENAME */
`endif
