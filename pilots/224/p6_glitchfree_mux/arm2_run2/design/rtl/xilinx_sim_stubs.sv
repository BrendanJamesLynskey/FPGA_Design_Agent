// Simulation-only stand-ins for Xilinx primitives; Vivado supplies the real ones in synthesis.
`ifndef SYNTHESIS
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off DECLFILENAME */
/* verilator lint_off MULTITOP */
/* verilator lint_off PROCASSINIT */

module xpm_cdc_single #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                        parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1)
    (input logic src_clk, input logic src_in, input logic dest_clk, output logic dest_out);
    logic [DEST_SYNC_FF-1:0] sr = '0;
    always_ff @(posedge dest_clk) sr <= {sr[DEST_SYNC_FF-2:0], src_in};
    assign dest_out = sr[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_array_single #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                              parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1,
                              parameter int WIDTH = 2)
    (input logic src_clk, input logic [WIDTH-1:0] src_in, input logic dest_clk, output logic [WIDTH-1:0] dest_out);
    logic [WIDTH-1:0] sr [DEST_SYNC_FF];
    initial for (int i = 0; i < DEST_SYNC_FF; i++) sr[i] = '0;
    always_ff @(posedge dest_clk) begin
        sr[0] <= src_in;
        for (int i = 1; i < DEST_SYNC_FF; i++) sr[i] <= sr[i-1];
    end
    assign dest_out = sr[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_gray #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                      parameter int REG_OUTPUT = 0, parameter int SIM_ASSERT_CHK = 0,
                      parameter int SIM_LOSSLESS_GRAY_CHK = 0, parameter int WIDTH = 2)
    (input logic src_clk, input logic [WIDTH-1:0] src_in_bin, input logic dest_clk,
     output logic [WIDTH-1:0] dest_out_bin);
    logic [WIDTH-1:0] g_src;
    logic [WIDTH-1:0] sr [DEST_SYNC_FF];
    logic [WIDTH-1:0] b;
    initial for (int i = 0; i < DEST_SYNC_FF; i++) sr[i] = '0;
    assign g_src = src_in_bin ^ (src_in_bin >> 1);
    always_ff @(posedge dest_clk) begin
        sr[0] <= g_src;
        for (int i = 1; i < DEST_SYNC_FF; i++) sr[i] <= sr[i-1];
    end
    always_comb begin
        b[WIDTH-1] = sr[DEST_SYNC_FF-1][WIDTH-1];
        for (int i = WIDTH-2; i >= 0; i--) b[i] = b[i+1] ^ sr[DEST_SYNC_FF-1][i];
    end
    assign dest_out_bin = b;
endmodule

module xpm_cdc_handshake #(parameter int DEST_EXT_HSK = 1, parameter int DEST_SYNC_FF = 4,
                           parameter int INIT_SYNC_FF = 0, parameter int SIM_ASSERT_CHK = 0,
                           parameter int SRC_SYNC_FF = 4, parameter int WIDTH = 1)
    (input logic src_clk, input logic [WIDTH-1:0] src_in, input logic src_send, output logic src_rcv,
     input logic dest_clk, output logic dest_req, input logic dest_ack, output logic [WIDTH-1:0] dest_out);
    logic req_f = 1'b0;
    logic [WIDTH-1:0] data_r = '0;
    logic [DEST_SYNC_FF-1:0] req_sr = '0;
    logic req_p = 1'b0;
    logic ack_d = 1'b0;
    logic [SRC_SYNC_FF-1:0] ack_sr = '0;
    logic rcv_s;
    assign rcv_s = ack_sr[SRC_SYNC_FF-1];
    assign src_rcv = rcv_s;
    always_ff @(posedge src_clk) begin
        ack_sr <= {ack_sr[SRC_SYNC_FF-2:0], ack_d};
        if (src_send && !req_f && !rcv_s) begin req_f <= 1'b1; data_r <= src_in; end
        else if (rcv_s) req_f <= 1'b0;
    end
    always_ff @(posedge dest_clk) begin
        req_sr <= {req_sr[DEST_SYNC_FF-2:0], req_f};
        req_p  <= req_sr[DEST_SYNC_FF-1];
        ack_d  <= req_sr[DEST_SYNC_FF-1];
    end
    assign dest_req = req_sr[DEST_SYNC_FF-1] & ~req_p;
    assign dest_out = data_r;
endmodule

module xpm_cdc_async_rst #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                           parameter int RST_ACTIVE_HIGH = 0)
    (input logic src_arst, input logic dest_clk, output logic dest_arst);
    logic [DEST_SYNC_FF-1:0] sr = '1;
    always_ff @(posedge dest_clk) begin
        if (src_arst == (RST_ACTIVE_HIGH != 0)) sr <= '1;
        else sr <= {sr[DEST_SYNC_FF-2:0], 1'b0};
    end
    assign dest_arst = (RST_ACTIVE_HIGH != 0) ? sr[DEST_SYNC_FF-1] : ~sr[DEST_SYNC_FF-1];
endmodule

module BUFGCTRL #(parameter int INIT_OUT = 0, parameter string PRESELECT_I0 = "FALSE",
                  parameter string PRESELECT_I1 = "FALSE", parameter bit IS_CE0_INVERTED = 1'b0,
                  parameter bit IS_CE1_INVERTED = 1'b0)
    (output logic O, input logic CE0, input logic CE1, input logic I0, input logic I1,
     input logic IGNORE0, input logic IGNORE1, input logic S0, input logic S1);
    // ideal select (behavioural only; the real cell gives glitch-free switching)
    assign O = S1 ? I1 : I0;
endmodule

module BUFG_GT #(parameter string SIM_DEVICE = "ULTRASCALE_PLUS")
    (output logic O, input logic CE, input logic CEMASK, input logic CLR, input logic CLRMASK,
     input logic [2:0] DIV, input logic I);
    assign O = I;
endmodule

module IBUFDS_GTE4 #(parameter bit REFCLK_EN_TX_PATH = 1'b0, parameter bit [1:0] REFCLK_HROW_CK_SEL = 2'b00,
                     parameter bit [1:0] REFCLK_ICNTL_RX = 2'b00)
    (output logic O, output logic ODIV2, input logic CEB, input logic I, input logic IB);
    assign O = I;
    assign ODIV2 = 1'b0;
endmodule

module USR_ACCESSE2 (output logic CFGCLK, output logic [31:0] DATA, output logic DATAVALID);
    assign CFGCLK = 1'b0;
    assign DATA = 32'h0;
    assign DATAVALID = 1'b1;
endmodule
`endif
