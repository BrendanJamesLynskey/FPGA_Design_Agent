`ifndef SYNTHESIS
/* verilator lint_off DECLFILENAME */
/* verilator lint_off UNUSEDPARAM */
// Simulation-only stand-ins for Xilinx primitives (Vivado supplies the real ones).
module xpm_cdc_single #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                        parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1) (
    input logic src_clk, input logic src_in, input logic dest_clk, output logic dest_out);
    logic [DEST_SYNC_FF-1:0] s;
    always_ff @(posedge dest_clk) s <= {s[DEST_SYNC_FF-2:0], src_in};
    assign dest_out = s[DEST_SYNC_FF-1];
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_clk;
    assign unused_clk = src_clk;
    /* verilator lint_on UNUSEDSIGNAL */
endmodule

module xpm_cdc_array_single #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                              parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1,
                              parameter int WIDTH = 2) (
    input logic src_clk, input logic [WIDTH-1:0] src_in, input logic dest_clk,
    output logic [WIDTH-1:0] dest_out);
    logic [WIDTH-1:0] s [DEST_SYNC_FF];
    always_ff @(posedge dest_clk) begin
        s[0] <= src_in;
        for (int i = 1; i < DEST_SYNC_FF; i++) s[i] <= s[i-1];
    end
    assign dest_out = s[DEST_SYNC_FF-1];
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_clk;
    assign unused_clk = src_clk;
    /* verilator lint_on UNUSEDSIGNAL */
endmodule

module xpm_cdc_async_rst #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                           parameter int RST_ACTIVE_HIGH = 0) (
    output logic dest_arst, input logic dest_clk, input logic src_arst);
    logic [DEST_SYNC_FF-1:0] s;
    always_ff @(posedge dest_clk)
        if (src_arst) s <= '1;
        else s <= {s[DEST_SYNC_FF-2:0], 1'b0};
    assign dest_arst = s[DEST_SYNC_FF-1];
endmodule

module USR_ACCESSE2 (output logic CFGCLK, output logic [31:0] DATA, output logic DATAVALID);
    assign CFGCLK = 1'b0;
    assign DATA = 32'd0;
    assign DATAVALID = 1'b0;
endmodule

module BUFG (input logic I, output logic O);
    assign O = I;
endmodule

module MMCME4_BASE #(parameter real CLKIN1_PERIOD = 10.0, parameter int DIVCLK_DIVIDE = 1,
                     parameter real CLKFBOUT_MULT_F = 5.0, parameter real CLKOUT0_DIVIDE_F = 1.0) (
    input logic CLKIN1, input logic CLKFBIN, output logic CLKFBOUT, output logic CLKOUT0,
    output logic LOCKED, input logic PWRDWN, input logic RST);
    assign CLKFBOUT = CLKIN1;
    assign CLKOUT0 = CLKIN1;
    assign LOCKED = 1'b1;
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused;
    assign unused = PWRDWN ^ RST ^ CLKFBIN;
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
`endif

