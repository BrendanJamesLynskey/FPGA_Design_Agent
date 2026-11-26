// Simulation-only stand-ins for Xilinx primitives (Vivado supplies the real ones).
`ifndef SYNTHESIS
/* verilator lint_off DECLFILENAME */
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNUSEDPARAM */
module USR_ACCESSE2 (output logic CFGCLK, output logic [31:0] DATA, output logic DATAVALID);
    assign CFGCLK = 1'b0;
    assign DATA = 32'h0;
    assign DATAVALID = 1'b1;
endmodule

module xpm_cdc_single #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                        parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1) (
    input  logic src_clk, input logic src_in, input logic dest_clk, output logic dest_out);
    logic [1:0] s;
    always_ff @(posedge dest_clk) s <= {s[0], src_in};
    assign dest_out = s[1];
endmodule

module xpm_cdc_array_single #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                              parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1,
                              parameter int WIDTH = 2) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in, input logic dest_clk,
    output logic [WIDTH-1:0] dest_out);
    logic [WIDTH-1:0] s0, s1;
    always_ff @(posedge dest_clk) begin s0 <= src_in; s1 <= s0; end
    assign dest_out = s1;
endmodule
/* verilator lint_on UNUSEDPARAM */
/* verilator lint_on UNUSEDSIGNAL */
`endif
