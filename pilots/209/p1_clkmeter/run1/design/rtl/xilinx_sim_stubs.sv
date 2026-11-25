// Simulation-only stand-ins for Xilinx primitives; Vivado supplies the real ones (SYNTHESIS is defined there).
`ifndef SYNTHESIS
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off PROCASSINIT */
/* verilator lint_off DECLFILENAME */
/* verilator lint_off MULTITOP */
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
    input  logic src_clk, input logic [WIDTH-1:0] src_in, input logic dest_clk, output logic [WIDTH-1:0] dest_out);
    logic [WIDTH-1:0] s [DEST_SYNC_FF];
    initial for (int i = 0; i < DEST_SYNC_FF; i++) s[i] = '0;
    always_ff @(posedge dest_clk) begin
        s[0] <= src_in;
        for (int i = 1; i < DEST_SYNC_FF; i++) s[i] <= s[i-1];
    end
    assign dest_out = s[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_async_rst #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                           parameter int RST_ACTIVE_HIGH = 0) (
    input  logic src_arst, input logic dest_clk, output logic dest_arst);
    logic [DEST_SYNC_FF-1:0] s = '0;
    always_ff @(posedge dest_clk) s <= {s[DEST_SYNC_FF-2:0], src_arst};
    assign dest_arst = s[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_handshake #(parameter int DEST_EXT_HSK = 1, parameter int DEST_SYNC_FF = 4,
                           parameter int INIT_SYNC_FF = 0, parameter int SIM_ASSERT_CHK = 0,
                           parameter int SRC_SYNC_FF = 4, parameter int WIDTH = 1) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in, input logic src_send, output logic src_rcv,
    input  logic dest_clk, output logic [WIDTH-1:0] dest_out, output logic dest_req, input logic dest_ack);
    logic req = 1'b0, sent = 1'b0, ack = 1'b0;
    logic [WIDTH-1:0] data = '0;
    logic a1 = 1'b0, a2 = 1'b0, r1 = 1'b0, r2 = 1'b0;
    initial begin src_rcv = 1'b0; dest_req = 1'b0; dest_out = '0; end
    always_ff @(posedge src_clk) begin
        a1 <= ack; a2 <= a1;
        if (src_send && !sent) begin data <= src_in; req <= ~req; sent <= 1'b1; end
        if (sent && (a2 == req)) src_rcv <= 1'b1;
        if (!src_send) begin sent <= 1'b0; src_rcv <= 1'b0; end
    end
    always_ff @(posedge dest_clk) begin
        r1 <= req; r2 <= r1;
        dest_req <= 1'b0;
        if (r2 != ack) begin dest_out <= data; dest_req <= 1'b1; ack <= r2; end
    end
endmodule

module IBUFDS_GTE4 #(parameter bit [0:0] REFCLK_EN_TX_PATH = 1'b0, parameter bit [1:0] REFCLK_HROW_CK_SEL = 2'b00,
                     parameter bit [1:0] REFCLK_ICNTL_RX = 2'b00) (
    input logic I, input logic IB, input logic CEB, output logic O, output logic ODIV2);
    assign O = I;
    assign ODIV2 = I;
endmodule

module BUFG_GT (input logic I, input logic CE, input logic CEMASK, input logic CLR, input logic CLRMASK,
                input logic [2:0] DIV, output logic O);
    assign O = I;
endmodule

module BUFG (input logic I, output logic O);
    assign O = I;
endmodule

module USR_ACCESSE2 (output logic [31:0] DATA, output logic CFGCLK, output logic DATAVALID);
    assign DATA = 32'h0;
    assign CFGCLK = 1'b0;
    assign DATAVALID = 1'b0;
endmodule
`endif
