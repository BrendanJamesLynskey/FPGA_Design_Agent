// Simulation-only stand-ins for Xilinx primitives (Vivado supplies the real ones in synthesis).
`ifndef SYNTHESIS
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off DECLFILENAME */
/* verilator lint_off WIDTHEXPAND */
/* verilator lint_off WIDTHTRUNC */
/* verilator lint_off PROCASSINIT */
/* verilator lint_off MULTITOP */
/* verilator lint_off UNDRIVEN */
/* verilator lint_off SYNCASYNCNET */

module xpm_cdc_single #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0, parameter int SIM_ASSERT_CHK = 0,
    parameter int SRC_INPUT_REG = 1, parameter int VERSION = 0
) (
    input  logic src_clk, input logic src_in, input logic dest_clk, output logic dest_out
);
    logic [DEST_SYNC_FF-1:0] q = '0;
    always_ff @(posedge dest_clk) q <= {q[DEST_SYNC_FF-2:0], src_in};
    assign dest_out = q[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_array_single #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0, parameter int SIM_ASSERT_CHK = 0,
    parameter int SRC_INPUT_REG = 1, parameter int VERSION = 0, parameter int WIDTH = 2
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in, input logic dest_clk, output logic [WIDTH-1:0] dest_out
);
    logic [WIDTH-1:0] q [DEST_SYNC_FF];
    initial for (int i = 0; i < DEST_SYNC_FF; i++) q[i] = '0;
    always_ff @(posedge dest_clk) begin
        q[0] <= src_in;
        for (int i = 1; i < DEST_SYNC_FF; i++) q[i] <= q[i-1];
    end
    assign dest_out = q[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_async_rst #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0, parameter int RST_ACTIVE_HIGH = 0,
    parameter int VERSION = 0
) (
    input  logic dest_clk, input logic src_arst, output logic dest_arst
);
    // behavioural model: asserted state shifted out synchronously
    logic [DEST_SYNC_FF-1:0] aq = '1;
    wire asserted = (src_arst == (RST_ACTIVE_HIGH != 0));
    always_ff @(posedge dest_clk) aq <= asserted ? '1 : {aq[DEST_SYNC_FF-2:0], 1'b0};
    assign dest_arst = (RST_ACTIVE_HIGH != 0) ? aq[DEST_SYNC_FF-1] : ~aq[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_handshake #(
    parameter int DEST_EXT_HSK = 1, parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_SYNC_FF = 4, parameter int VERSION = 0,
    parameter int WIDTH = 1
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in, input logic src_send, output logic src_rcv,
    input  logic dest_clk, output logic dest_req, input logic dest_ack, output logic [WIDTH-1:0] dest_out
);
    logic tog_s = 1'b0, pending = 1'b0, rcv = 1'b0;
    logic [WIDTH-1:0] data_s = '0;
    logic [1:0] ack_ss = '0;
    logic [1:0] tog_d = '0;
    logic last_d = 1'b0, ack_t = 1'b0;
    logic req_q = 1'b0;
    logic [WIDTH-1:0] out_q = '0;
    always_ff @(posedge src_clk) begin
        ack_ss <= {ack_ss[0], ack_t};
        if (src_send && !pending && !rcv) begin data_s <= src_in; tog_s <= ~tog_s; pending <= 1'b1; end
        if (pending && ack_ss[1] == tog_s) begin pending <= 1'b0; rcv <= 1'b1; end
        if (!src_send) rcv <= 1'b0;
    end
    always_ff @(posedge dest_clk) begin
        tog_d <= {tog_d[0], tog_s};
        last_d <= tog_d[1];
        req_q <= (tog_d[1] != last_d);
        if (tog_d[1] != last_d) out_q <= data_s;
        ack_t <= tog_d[1];
    end
    assign src_rcv = rcv;
    assign dest_req = req_q;
    assign dest_out = out_q;
endmodule

// Behavioural glitch-free clock mux (each clock enables itself only after the other has been disabled).
module BUFGCTRL #(
    parameter int INIT_OUT = 0, parameter string PRESELECT_I0 = "FALSE", parameter string PRESELECT_I1 = "FALSE"
) (
    input logic I0, input logic I1, input logic S0, input logic S1, input logic CE0, input logic CE1,
    input logic IGNORE0, input logic IGNORE1, output logic O
);
    logic en0, en1;
    bufgctrl_sim_half #(.PRE(PRESELECT_I0 == "TRUE")) u_h0 (.clk(I0), .ce(CE0), .s(S0), .other_en(en1), .en(en0));
    bufgctrl_sim_half #(.PRE(PRESELECT_I1 == "TRUE")) u_h1 (.clk(I1), .ce(CE1), .s(S1), .other_en(en0), .en(en1));
    assign O = (I0 & en0) | (I1 & en1);
endmodule
// One half of the behavioural mux: a single clock, enable updated on its falling edge.
module bufgctrl_sim_half #(parameter bit PRE = 1'b0) (
    input logic clk, input logic ce, input logic s, input logic other_en, output logic en
);
    initial en = PRE;
    always_ff @(negedge clk) if (ce) en <= s & ~other_en;
endmodule
module xpm_cdc_gray #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0, parameter int REG_OUTPUT = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SIM_LOSSLESS_GRAY_CHK = 0, parameter int VERSION = 0,
    parameter int WIDTH = 2
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in_bin, input logic dest_clk, output logic [WIDTH-1:0] dest_out_bin
);
    logic [WIDTH-1:0] g_s = '0;
    logic [WIDTH-1:0] q [DEST_SYNC_FF];
    initial for (int i = 0; i < DEST_SYNC_FF; i++) q[i] = '0;
    always_ff @(posedge src_clk) g_s <= src_in_bin ^ (src_in_bin >> 1);
    always_ff @(posedge dest_clk) begin
        q[0] <= g_s;
        for (int i = 1; i < DEST_SYNC_FF; i++) q[i] <= q[i-1];
    end
    always_comb begin
        dest_out_bin[WIDTH-1] = q[DEST_SYNC_FF-1][WIDTH-1];
        for (int i = WIDTH-2; i >= 0; i--) dest_out_bin[i] = dest_out_bin[i+1] ^ q[DEST_SYNC_FF-1][i];
    end
endmodule

module IBUFDS_GTE4 #(
    parameter bit [1:0] REFCLK_EN_TX_PATH = 1'b0, parameter bit [4:0] REFCLK_HROW_CK_SEL = 2'b00,
    parameter bit [1:0] REFCLK_ICNTL_RX = 2'b00
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
/* verilator lint_on DECLFILENAME */
/* verilator lint_on UNUSEDPARAM */
/* verilator lint_on UNUSEDSIGNAL */
`endif
