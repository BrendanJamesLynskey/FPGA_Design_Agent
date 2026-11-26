// Simulation-only stand-ins for Xilinx primitives (Vivado supplies the real ones in synthesis).
`ifndef SYNTHESIS
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off DECLFILENAME */
/* verilator lint_off PROCASSINIT */
/* verilator lint_off SYNCASYNCNET */
/* verilator lint_off UNUSEDSIGNAL */
module xpm_cdc_single #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1
) (
    input  logic src_clk, input logic src_in, input logic dest_clk, output logic dest_out
);
    logic [DEST_SYNC_FF-1:0] ch = '0;
    always_ff @(posedge dest_clk) ch <= {ch[DEST_SYNC_FF-2:0], src_in};
    assign dest_out = ch[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_array_single #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1, parameter int WIDTH = 2
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in, input logic dest_clk,
    output logic [WIDTH-1:0] dest_out
);
    logic [WIDTH-1:0] ch [DEST_SYNC_FF];
    initial for (int i = 0; i < DEST_SYNC_FF; i++) ch[i] = '0;
    always_ff @(posedge dest_clk) begin
        ch[0] <= src_in;
        for (int i = 1; i < DEST_SYNC_FF; i++) ch[i] <= ch[i-1];
    end
    assign dest_out = ch[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_async_rst #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0, parameter int RST_ACTIVE_HIGH = 0
) (
    input logic src_arst, input logic dest_clk, output logic dest_arst
);
    // simulation model only: both edges pass through the synchroniser chain
    logic [DEST_SYNC_FF-1:0] ch = '1;
    always_ff @(posedge dest_clk) ch <= {ch[DEST_SYNC_FF-2:0], src_arst};
    assign dest_arst = ch[DEST_SYNC_FF-1];
endmodule

module USR_ACCESSE2 (output logic CFGCLK, output logic [31:0] DATA, output logic DATAVALID);
    assign CFGCLK = 1'b0;
    assign DATA = 32'd0;
    assign DATAVALID = 1'b0;
endmodule

module IBUFDS_GTE4 (input logic I, input logic IB, input logic CEB, output logic O, output logic ODIV2);
    assign O = I;
    assign ODIV2 = I;
endmodule

module BUFG_GT (input logic I, input logic CE, input logic CEMASK, input logic CLR, input logic CLRMASK,
                input logic [2:0] DIV, output logic O);
    assign O = I;
endmodule
`endif
// The supplied data/jtag_bus.sv (compiled after rtl/) is read-only; its unused tdo/cmd_s[45] are deliberate.
/* verilator lint_off UNUSEDSIGNAL */
