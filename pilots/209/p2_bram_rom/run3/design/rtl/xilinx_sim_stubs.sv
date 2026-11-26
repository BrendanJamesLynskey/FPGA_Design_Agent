// Simulation-only stand-ins; Vivado supplies the real primitives in synthesis.
`ifndef SYNTHESIS
/* verilator lint_off DECLFILENAME */
/* verilator lint_off UNUSEDPARAM */
module USR_ACCESSE2 (
    output logic        CFGCLK,
    output logic [31:0] DATA,
    output logic        DATAVALID
);
    assign CFGCLK = 1'b0;
    assign DATA = 32'd0;
    assign DATAVALID = 1'b1;
endmodule

module xpm_cdc_single #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1
) (
    input  logic src_clk, input logic src_in, input logic dest_clk, output logic dest_out
);
    logic [DEST_SYNC_FF-1:0] s;
    always_ff @(posedge dest_clk) s <= {s[DEST_SYNC_FF-2:0], src_in};
    assign dest_out = s[DEST_SYNC_FF-1];
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_c;
    assign unused_c = src_clk;
    /* verilator lint_on UNUSEDSIGNAL */
endmodule

module xpm_cdc_array_single #(
    parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
    parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1, parameter int WIDTH = 2
) (
    input  logic src_clk, input logic [WIDTH-1:0] src_in,
    input  logic dest_clk, output logic [WIDTH-1:0] dest_out
);
    logic [WIDTH-1:0] s [DEST_SYNC_FF];
    always_ff @(posedge dest_clk) begin
        s[0] <= src_in;
        for (int i = 1; i < DEST_SYNC_FF; i++) s[i] <= s[i-1];
    end
    assign dest_out = s[DEST_SYNC_FF-1];
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_c;
    assign unused_c = src_clk;
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
`endif
