// Simulation-only stand-ins for Xilinx primitives (Vivado supplies the real ones in synthesis).
`ifndef SYNTHESIS
/* verilator lint_off UNUSEDSIGNAL */
module xpm_cdc_single #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1
) (
    input  logic src_clk, input logic src_in, input logic dest_clk, output logic dest_out
);
    logic a, b;
    initial begin a = 1'b0; b = 1'b0; end
    always @(posedge dest_clk) begin a <= src_in; b <= a; end
    assign dest_out = b;
endmodule

module xpm_cdc_array_single #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1, parameter int WIDTH = 2
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in, input logic dest_clk,
    output logic [WIDTH-1:0] dest_out
);
    logic [WIDTH-1:0] a, b, s;
    initial begin a = '0; b = '0; s = '0; end
    always @(posedge src_clk) s <= src_in;
    always @(posedge dest_clk) begin a <= (SRC_INPUT_REG != 0) ? s : src_in; b <= a; end
    assign dest_out = b;
endmodule

module xpm_cdc_async_rst #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0, parameter int RST_ACTIVE_HIGH = 1
) (
    input logic src_arst, input logic dest_clk, output logic dest_arst
);
    logic a, b;
    initial begin a = 1'b0; b = 1'b0; end
    always @(posedge dest_clk or posedge src_arst) begin
        if (src_arst) begin a <= 1'b1; b <= 1'b1; end
        else begin a <= 1'b0; b <= a; end
    end
    assign dest_arst = b;
endmodule

module xpm_cdc_handshake #(
    parameter int DEST_EXT_HSK = 0, parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_SYNC_FF = 4, parameter int WIDTH = 8
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in, input logic src_send, output logic src_rcv,
    input  logic dest_clk, output logic dest_req, input logic dest_ack, output logic [WIDTH-1:0] dest_out
);
    logic req_t, ack_t, sent, rcv_r;
    logic [1:0] ack_s, req_s;
    logic req_d;
    logic [WIDTH-1:0] hold_d;
    initial begin
        req_t = 1'b0; ack_t = 1'b0; sent = 1'b0; rcv_r = 1'b0; ack_s = '0; req_s = '0; req_d = 1'b0;
        hold_d = '0; dest_out = '0; dest_req = 1'b0;
    end
    always @(posedge src_clk) begin
        ack_s <= {ack_s[0], ack_t};
        if (src_send && !sent && !rcv_r) begin hold_d <= src_in; req_t <= ~req_t; sent <= 1'b1; end
        if (sent && ack_s[1] == req_t) begin rcv_r <= 1'b1; sent <= 1'b0; end
        if (!src_send) rcv_r <= 1'b0;
    end
    always @(posedge dest_clk) begin
        req_s <= {req_s[0], req_t};
        req_d <= req_s[1];
        dest_req <= 1'b0;
        if (req_s[1] != req_d) begin dest_out <= hold_d; dest_req <= 1'b1; ack_t <= req_s[1]; end
    end
    assign src_rcv = rcv_r;
endmodule

module BUFG (input logic I, output logic O);
    assign O = I;
endmodule

module IBUFDS_GTE4 #(
    parameter logic [1:0] REFCLK_EN_TX_PATH = 2'b00, parameter logic [4:0] REFCLK_HROW_CK_SEL = 5'b00000,
    parameter logic [1:0] REFCLK_ICNTL_RX = 2'b00
) (
    input logic I, input logic IB, input logic CEB, output logic O, output logic ODIV2
);
    assign O = I;
    assign ODIV2 = I;
endmodule

module BUFG_GT (
    input logic I, input logic CE, input logic CEMASK, input logic CLR, input logic CLRMASK,
    input logic [2:0] DIV, output logic O
);
    assign O = I;
endmodule

module USR_ACCESSE2 (output logic [31:0] DATA, output logic CFGCLK, output logic DATAVALID);
    assign DATA = 32'h0;
    assign CFGCLK = 1'b0;
    assign DATAVALID = 1'b0;
endmodule
`endif
