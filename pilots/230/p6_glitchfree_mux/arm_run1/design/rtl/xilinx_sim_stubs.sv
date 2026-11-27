// Simulation-only stand-ins for Xilinx primitives; Vivado supplies the real ones in synthesis.
`ifndef SYNTHESIS
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off DECLFILENAME */
/* verilator lint_off MULTITOP */

module xpm_cdc_single #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1
) (
    input  logic src_clk, input logic src_in, input logic dest_clk, output logic dest_out
);
    logic [DEST_SYNC_FF-1:0] q = '0;
    always_ff @(posedge dest_clk) q <= {q[DEST_SYNC_FF-2:0], src_in};
    assign dest_out = q[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_array_single #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1, parameter int WIDTH = 2
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in, input logic dest_clk, output logic [WIDTH-1:0] dest_out
);
    logic [WIDTH-1:0] q [DEST_SYNC_FF];
    always_ff @(posedge dest_clk) begin
        q[0] <= src_in;
        for (int i = 1; i < DEST_SYNC_FF; i++) q[i] <= q[i-1];
    end
    assign dest_out = q[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_async_rst #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0, parameter int RST_ACTIVE_HIGH = 0
) (
    input logic src_arst, input logic dest_clk, output logic dest_arst
);
    logic [DEST_SYNC_FF-1:0] q;
    always_ff @(posedge dest_clk or posedge src_arst) begin
        if (src_arst) q <= '1;
        else          q <= {q[DEST_SYNC_FF-2:0], 1'b0};
    end
    assign dest_arst = q[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_handshake #(
    parameter int DEST_EXT_HSK = 1, parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_SYNC_FF = 4, parameter int WIDTH = 1
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in, input logic src_send, output logic src_rcv,
    input  logic dest_clk, output logic [WIDTH-1:0] dest_out, output logic dest_req, input logic dest_ack
);
    logic [WIDTH-1:0] data_s = '0;
    logic req_t = 1'b0, busy = 1'b0;
    logic [DEST_SYNC_FF-1:0] req_sync = '0;
    logic req_prev = 1'b0;
    logic ack_t = 1'b0;
    logic [SRC_SYNC_FF-1:0] ack_sync = '0;
    initial begin src_rcv = 1'b0; dest_out = '0; dest_req = 1'b0; end

    always_ff @(posedge src_clk) begin
        ack_sync <= {ack_sync[SRC_SYNC_FF-2:0], ack_t};
        if (!src_send) src_rcv <= 1'b0;
        if (src_send && !busy && !src_rcv) begin
            data_s <= src_in; req_t <= ~req_t; busy <= 1'b1;
        end else if (busy && (ack_sync[SRC_SYNC_FF-1] == req_t)) begin
            busy <= 1'b0; src_rcv <= 1'b1;
        end
    end

    always_ff @(posedge dest_clk) begin
        req_sync <= {req_sync[DEST_SYNC_FF-2:0], req_t};
        req_prev <= req_sync[DEST_SYNC_FF-1];
        dest_req <= 1'b0;
        if (req_sync[DEST_SYNC_FF-1] != req_prev) begin
            dest_req <= 1'b1; dest_out <= data_s; ack_t <= req_sync[DEST_SYNC_FF-1];
        end
    end
endmodule

module BUFGCTRL #(
    parameter int INIT_OUT = 0, parameter string PRESELECT_I0 = "FALSE",
    parameter string PRESELECT_I1 = "FALSE", parameter string SIM_DEVICE = "ULTRASCALE_PLUS"
) (
    output logic O, input logic I0, input logic I1, input logic S0, input logic S1,
    input logic CE0, input logic CE1, input logic IGNORE0, input logic IGNORE1
);
    assign O = (S1 && CE1) ? I1 : I0;
endmodule

module USR_ACCESSE2 (output logic [31:0] DATA, output logic DATAVALID, output logic CFGCLK);
    assign DATA = 32'd0;
    assign DATAVALID = 1'b0;
    assign CFGCLK = 1'b0;
endmodule

module IBUFDS_GTE4 #(parameter bit [1:0] REFCLK_HROW_CK_SEL = 2'b00) (
    input logic I, input logic IB, input logic CEB, output logic O, output logic ODIV2
);
    assign O = I;
    assign ODIV2 = I;
endmodule

module BUFG_GT #(parameter string SIM_DEVICE = "ULTRASCALE_PLUS") (
    input logic I, input logic CE, input logic CEMASK, input logic CLR, input logic CLRMASK,
    input logic [2:0] DIV, output logic O
);
    assign O = I;
endmodule
`endif
