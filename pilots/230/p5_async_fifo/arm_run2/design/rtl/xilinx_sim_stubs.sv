// Simulation-only stand-ins for Xilinx primitives (Vivado supplies the real ones in synthesis).
`ifndef SYNTHESIS

module USR_ACCESSE2 (
    output logic [31:0] DATA,
    output logic        DATAVALID,
    output logic        CFGCLK
);
    assign DATA = 32'd0;
    assign DATAVALID = 1'b1;
    assign CFGCLK = 1'b0;
endmodule

module IBUFDS_GTE4 #(
    parameter [0:0] REFCLK_EN_TX_PATH = 1'b0,
    parameter [1:0] REFCLK_HROW_CK_SEL = 2'b00,
    parameter [1:0] REFCLK_ICNTL_RX = 2'b00
) (
    output logic O,
    output logic ODIV2,
    input  logic CEB,
    input  logic I,
    input  logic IB
);
    assign O = I & ~CEB;
    assign ODIV2 = I & ~CEB;
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_ib;
    assign unused_ib = IB;
    /* verilator lint_on UNUSEDSIGNAL */
endmodule

module BUFG_GT (
    output logic       O,
    input  logic       CE,
    input  logic       CEMASK,
    input  logic       CLR,
    input  logic       CLRMASK,
    input  logic [2:0] DIV,
    input  logic       I
);
    assign O = I;
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_bg;
    assign unused_bg = &{CE, CEMASK, CLR, CLRMASK, DIV};
    /* verilator lint_on UNUSEDSIGNAL */
endmodule

module xpm_cdc_single #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1
) (
    input  logic src_clk, input logic src_in,
    input  logic dest_clk, output logic dest_out
);
    logic [DEST_SYNC_FF-1:0] sr = '0;
    always_ff @(posedge dest_clk) sr <= {sr[DEST_SYNC_FF-2:0], src_in};
    assign dest_out = sr[DEST_SYNC_FF-1];
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_c;
    assign unused_c = src_clk;
    /* verilator lint_on UNUSEDSIGNAL */
endmodule

module xpm_cdc_array_single #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1, parameter int WIDTH = 2
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in,
    input  logic dest_clk, output logic [WIDTH-1:0] dest_out
);
    logic [WIDTH-1:0] sr [0:DEST_SYNC_FF-1];
    initial for (int i = 0; i < DEST_SYNC_FF; i++) sr[i] = '0;
    always_ff @(posedge dest_clk) begin
        sr[0] <= src_in;
        for (int i = 1; i < DEST_SYNC_FF; i++) sr[i] <= sr[i-1];
    end
    assign dest_out = sr[DEST_SYNC_FF-1];
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_c;
    assign unused_c = src_clk;
    /* verilator lint_on UNUSEDSIGNAL */
endmodule

module xpm_cdc_gray #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0, parameter int REG_OUTPUT = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SIM_LOSSLESS_GRAY_CHK = 0, parameter int WIDTH = 2
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in_bin,
    input  logic dest_clk, output logic [WIDTH-1:0] dest_out_bin
);
    logic [WIDTH-1:0] g_src = '0;
    logic [WIDTH-1:0] sr [0:DEST_SYNC_FF-1];
    initial for (int i = 0; i < DEST_SYNC_FF; i++) sr[i] = '0;
    always_ff @(posedge src_clk) g_src <= src_in_bin ^ (src_in_bin >> 1);
    always_ff @(posedge dest_clk) begin
        sr[0] <= g_src;
        for (int i = 1; i < DEST_SYNC_FF; i++) sr[i] <= sr[i-1];
    end
    always_comb begin
        dest_out_bin[WIDTH-1] = sr[DEST_SYNC_FF-1][WIDTH-1];
        for (int i = WIDTH-2; i >= 0; i--) dest_out_bin[i] = dest_out_bin[i+1] ^ sr[DEST_SYNC_FF-1][i];
    end
endmodule

module xpm_cdc_pulse #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0, parameter int REG_OUTPUT = 0,
    parameter int RST_USED = 1, parameter int SIM_ASSERT_CHK = 0
) (
    input  logic src_clk, input logic src_rst, input logic src_pulse,
    input  logic dest_clk, input logic dest_rst, output logic dest_pulse
);
    logic tog = 1'b0;
    logic [DEST_SYNC_FF-1:0] sr = '0;
    logic prev = 1'b0;
    always_ff @(posedge src_clk) if (src_pulse) tog <= ~tog;
    always_ff @(posedge dest_clk) begin
        sr   <= {sr[DEST_SYNC_FF-2:0], tog};
        prev <= sr[DEST_SYNC_FF-1];
    end
    assign dest_pulse = sr[DEST_SYNC_FF-1] ^ prev;
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_r;
    assign unused_r = src_rst ^ dest_rst;
    /* verilator lint_on UNUSEDSIGNAL */
endmodule

module xpm_cdc_handshake #(
    parameter int DEST_EXT_HSK = 1, parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_SYNC_FF = 4, parameter int WIDTH = 1
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in, input logic src_send, output logic src_rcv,
    input  logic dest_clk, output logic [WIDTH-1:0] dest_out, output logic dest_req, input logic dest_ack
);
    logic req_t = 1'b0, ack_t = 1'b0, busy = 1'b0, rcv = 1'b0;
    logic [WIDTH-1:0] data = '0;
    logic [SRC_SYNC_FF-1:0]  a_sr = '0;
    logic [DEST_SYNC_FF:0]   r_sr = '0;
    always_ff @(posedge src_clk) begin
        a_sr <= {a_sr[SRC_SYNC_FF-2:0], ack_t};
        if (!busy && !rcv && src_send) begin
            data <= src_in; req_t <= ~req_t; busy <= 1'b1;
        end else if (busy && a_sr[SRC_SYNC_FF-1] == req_t) begin
            busy <= 1'b0; rcv <= 1'b1;
        end else if (rcv && !src_send) rcv <= 1'b0;
    end
    assign src_rcv = rcv;
    always_ff @(posedge dest_clk) begin
        r_sr <= {r_sr[DEST_SYNC_FF-1:0], req_t};
        dest_req <= 1'b0;
        if (r_sr[DEST_SYNC_FF] != r_sr[DEST_SYNC_FF-1]) begin
            dest_out <= data; dest_req <= 1'b1; ack_t <= r_sr[DEST_SYNC_FF-1];
        end
    end
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_a;
    assign unused_a = dest_ack;
    /* verilator lint_on UNUSEDSIGNAL */
endmodule

`endif




