`ifndef SYNTHESIS
/* verilator lint_off DECLFILENAME */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off UNUSEDSIGNAL */
module USR_ACCESSE2 (output logic [31:0] DATA, output logic DATAVALID);
    assign DATA = 32'h0;
    assign DATAVALID = 1'b1;
endmodule

module xpm_cdc_single #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                        parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1) (
    input logic src_clk, input logic src_in, input logic dest_clk, output logic dest_out);
    assign dest_out = src_in;
endmodule

module xpm_cdc_array_single #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                              parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1,
                              parameter int WIDTH = 2) (
    input logic src_clk, input logic [WIDTH-1:0] src_in, input logic dest_clk,
    output logic [WIDTH-1:0] dest_out);
    assign dest_out = src_in;
endmodule
`endif
