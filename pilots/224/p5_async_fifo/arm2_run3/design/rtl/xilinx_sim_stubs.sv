// Simulation-only stand-ins for Xilinx primitives (Vivado supplies the real ones in synthesis).
`ifndef SYNTHESIS
/* verilator lint_off DECLFILENAME */

/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off PROCASSINIT */
/* verilator lint_off MULTITOP */

module USR_ACCESSE2 (
    output logic        CFGCLK,
    output logic [31:0] DATA,
    output logic        DATAVALID
);
    assign CFGCLK    = 1'b0;
    assign DATA      = 32'h0;
    assign DATAVALID = 1'b1;
endmodule

module IBUFDS_GTE4 #(
    parameter [0:0] REFCLK_EN_TX_PATH = 1'b0,
    parameter [1:0] REFCLK_HROW_CK_SEL = 2'b00,
    parameter [1:0] REFCLK_ICNTL_RX = 2'b00
) (
    input  logic I,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic IB,
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic CEB,
    output logic O,
    output logic ODIV2
);
    assign O     = I & ~CEB;
    assign ODIV2 = I & ~CEB;
endmodule

module BUFG_GT (
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic       CE,
    input  logic [2:0] CEMASK,
    input  logic       CLR,
    input  logic [2:0] CLRMASK,
    input  logic [2:0] DIV,
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic       I,
    output logic       O
);
    assign O = I;
endmodule

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
    xpm_cdc_array_single #(.DEST_SYNC_FF(DEST_SYNC_FF), .INIT_SYNC_FF(INIT_SYNC_FF), .SIM_ASSERT_CHK(SIM_ASSERT_CHK),
        .SRC_INPUT_REG(SRC_INPUT_REG), .WIDTH(1)) u_s (
        .src_clk(src_clk), .src_in(src_in), .dest_clk(dest_clk), .dest_out(dest_out));
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
    logic [WIDTH-1:0] src_q = '0;
    logic [WIDTH-1:0] sync [DEST_SYNC_FF];
    initial for (int i = 0; i < DEST_SYNC_FF; i++) sync[i] = '0;
    always_ff @(posedge src_clk) src_q <= src_in;
    always_ff @(posedge dest_clk) begin
        sync[0] <= (SRC_INPUT_REG != 0) ? src_q : src_in;
        for (int i = 1; i < DEST_SYNC_FF; i++) sync[i] <= sync[i-1];
    end
    assign dest_out = sync[DEST_SYNC_FF-1];
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
    logic [WIDTH-1:0] gray_q = '0;
    logic [WIDTH-1:0] sync [DEST_SYNC_FF];
    initial for (int i = 0; i < DEST_SYNC_FF; i++) sync[i] = '0;
    always_ff @(posedge src_clk) gray_q <= src_in_bin ^ (src_in_bin >> 1);
    always_ff @(posedge dest_clk) begin
        sync[0] <= gray_q;
        for (int i = 1; i < DEST_SYNC_FF; i++) sync[i] <= sync[i-1];
    end
    always_comb begin
        dest_out_bin[WIDTH-1] = sync[DEST_SYNC_FF-1][WIDTH-1];
        for (int i = WIDTH-2; i >= 0; i--)
            dest_out_bin[i] = dest_out_bin[i+1] ^ sync[DEST_SYNC_FF-1][i];
    end
endmodule

module xpm_cdc_async_rst #(
    parameter integer DEST_SYNC_FF = 4,
    parameter integer INIT_SYNC_FF = 0,
    parameter integer RST_ACTIVE_HIGH = 0
) (
    input  logic dest_clk,
    input  logic src_arst,
    output logic dest_arst
);
    localparam logic ACT = (RST_ACTIVE_HIGH != 0);
    logic [DEST_SYNC_FF-1:0] ff = {DEST_SYNC_FF{ACT}};
    always_ff @(posedge dest_clk) begin
        if (src_arst) ff <= {DEST_SYNC_FF{ACT}};
        else          ff <= {ff[DEST_SYNC_FF-2:0], ~ACT};
    end
    assign dest_arst = ff[DEST_SYNC_FF-1];
endmodule

// Handshake model: src_send held with src_in stable until src_rcv; dest_req pulses
// with dest_out valid (DEST_EXT_HSK = 0 behaviour).
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
    output logic             dest_req,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic             dest_ack,
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [WIDTH-1:0] dest_out
);
    logic [WIDTH-1:0] data_q = '0;
    logic req_t = 1'b0, pending = 1'b0, rcv_q = 1'b0;
    logic [SRC_SYNC_FF-1:0]  ack_s = '0;
    logic [DEST_SYNC_FF-1:0] req_s = '0;
    logic ack_t = 1'b0, dprev = 1'b0, dreq = 1'b0;
    logic [WIDTH-1:0] dout = '0;

    always_ff @(posedge src_clk) begin
        ack_s <= {ack_s[SRC_SYNC_FF-2:0], ack_t};
        if (src_send && !pending && !rcv_q) begin
            data_q <= src_in; req_t <= ~req_t; pending <= 1'b1;
        end
        if (pending && (ack_s[SRC_SYNC_FF-1] == req_t)) begin
            pending <= 1'b0; rcv_q <= 1'b1;
        end
        if (rcv_q && !src_send) rcv_q <= 1'b0;
    end
    assign src_rcv = rcv_q;

    always_ff @(posedge dest_clk) begin
        req_s <= {req_s[DEST_SYNC_FF-2:0], req_t};
        dprev <= req_s[DEST_SYNC_FF-1];
        dreq  <= 1'b0;
        if (req_s[DEST_SYNC_FF-1] != dprev) begin
            dout  <= data_q;
            dreq  <= 1'b1;
            ack_t <= req_s[DEST_SYNC_FF-1];
        end
    end
    assign dest_out = dout;
    assign dest_req = dreq;
endmodule

`endif
// Waiver: the supplied read-only data/jtag_bus.sv has an unused tdo and cmd_s[45]; it cannot be edited.
/* verilator lint_off UNUSEDSIGNAL */
