// Simulation-only stand-ins for Xilinx primitives (Vivado supplies the real ones in synthesis).
`ifndef SYNTHESIS
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off DECLFILENAME */
/* verilator lint_off MULTITOP */
/* verilator lint_off PROCASSINIT */

module BSCANE2 #(parameter int JTAG_CHAIN = 1) (
    output logic TCK, TDI, TDO, SEL, SHIFT, CAPTURE, UPDATE, DRCK, RESET, RUNTEST, TMS
);
    assign {TCK, TDI, TDO, SEL, SHIFT, CAPTURE, UPDATE, DRCK, RESET, RUNTEST, TMS} = '0;
endmodule

module USR_ACCESSE2 (output logic CFGCLK, output logic [31:0] DATA, output logic DATAVALID);
    assign CFGCLK = 1'b0;
    assign DATA = 32'd0;
    assign DATAVALID = 1'b1;
endmodule

module BUFG (input logic I, output logic O);
    assign O = I;
endmodule

module IBUFDS_GTE4 #(parameter bit REFCLK_EN_TX_PATH = 1'b0, parameter bit [1:0] REFCLK_HROW_CK_SEL = 2'b00,
                     parameter bit [1:0] REFCLK_ICNTL_RX = 2'b00)
    (input logic I, IB, CEB, output logic O, ODIV2);
    assign O = I;
    assign ODIV2 = I;
endmodule

module BUFG_GT (input logic I, CE, CEMASK, CLR, CLRMASK, input logic [2:0] DIV, output logic O);
    assign O = I;
endmodule

module xpm_cdc_single #(parameter int DEST_SYNC_FF = 4, INIT_SYNC_FF = 0, SIM_ASSERT_CHK = 0, SRC_INPUT_REG = 1)
    (input logic src_clk, src_in, dest_clk, output logic dest_out);
    logic [DEST_SYNC_FF-1:0] sr = '0;
    always_ff @(posedge dest_clk) sr <= {sr[DEST_SYNC_FF-2:0], src_in};
    assign dest_out = sr[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_array_single #(parameter int DEST_SYNC_FF = 4, INIT_SYNC_FF = 0, SIM_ASSERT_CHK = 0,
                              SRC_INPUT_REG = 1, WIDTH = 2)
    (input logic src_clk, input logic [WIDTH-1:0] src_in, input logic dest_clk, output logic [WIDTH-1:0] dest_out);
    logic [WIDTH-1:0] sr [DEST_SYNC_FF];
    initial for (int i = 0; i < DEST_SYNC_FF; i++) sr[i] = '0;
    always_ff @(posedge dest_clk) begin
        sr[0] <= src_in;
        for (int i = 1; i < DEST_SYNC_FF; i++) sr[i] <= sr[i-1];
    end
    assign dest_out = sr[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_async_rst #(parameter int DEST_SYNC_FF = 4, INIT_SYNC_FF = 0, RST_ACTIVE_HIGH = 0)
    (input logic src_arst, dest_clk, output logic dest_arst);
    logic [DEST_SYNC_FF-1:0] sr = '1;
    always_ff @(posedge dest_clk) sr <= {sr[DEST_SYNC_FF-2:0], src_arst};
    assign dest_arst = sr[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_handshake #(parameter int DEST_EXT_HSK = 1, DEST_SYNC_FF = 4, INIT_SYNC_FF = 0, SIM_ASSERT_CHK = 0,
                           SRC_SYNC_FF = 4, WIDTH = 1)
    (input logic src_clk, input logic [WIDTH-1:0] src_in, input logic src_send, output logic src_rcv,
     input logic dest_clk, output logic [WIDTH-1:0] dest_out, output logic dest_req, input logic dest_ack);
    logic sreq = 1'b0;
    logic [WIDTH-1:0] hold = '0;
    always_ff @(posedge src_clk) begin
        sreq <= src_send;
        if (src_send && !sreq) hold <= src_in;
    end
    logic [1:0] d_sr = '0;
    logic       dq = 1'b0;
    always_ff @(posedge dest_clk) begin
        d_sr <= {d_sr[0], sreq};
        dq   <= d_sr[1];
    end
    assign dest_out = hold;
    assign dest_req = d_sr[1] && !dq;
    logic [1:0] a_sr = '0;
    always_ff @(posedge src_clk) a_sr <= {a_sr[0], d_sr[1]};
    assign src_rcv = a_sr[1];
endmodule
/* verilator lint_on MULTITOP */
/* verilator lint_on DECLFILENAME */
/* verilator lint_on UNUSEDPARAM */
/* verilator lint_on UNUSEDSIGNAL */
`endif
