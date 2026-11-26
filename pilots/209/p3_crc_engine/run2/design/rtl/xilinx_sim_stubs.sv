// Simulation-only stand-ins for Xilinx primitives; Vivado supplies the real ones in synthesis.
`ifndef SYNTHESIS
/* verilator lint_off DECLFILENAME */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off UNUSEDSIGNAL */
module USR_ACCESSE2 (output logic CFGCLK, output logic [31:0] DATA, output logic DATAVALID);
    assign CFGCLK = 1'b0;
    assign DATA = 32'h0;
    assign DATAVALID = 1'b1;
endmodule

module BUFG (input logic I, output logic O);
    assign O = I;
endmodule

module MMCME4_BASE #(parameter real CLKIN1_PERIOD = 40.0, parameter real CLKFBOUT_MULT_F = 40.0,
                     parameter int DIVCLK_DIVIDE = 1, parameter real CLKOUT0_DIVIDE_F = 10.0) (
    input  logic CLKIN1, input logic CLKFBIN, output logic CLKFBOUT, output logic CLKOUT0, output logic LOCKED,
    input  logic PWRDWN, input logic RST,
    output logic CLKFBOUTB, output logic CLKOUT0B, output logic CLKOUT1, output logic CLKOUT1B,
    output logic CLKOUT2, output logic CLKOUT2B, output logic CLKOUT3, output logic CLKOUT3B,
    output logic CLKOUT4, output logic CLKOUT5, output logic CLKOUT6);
    assign {CLKFBOUT, CLKOUT0, LOCKED, CLKFBOUTB, CLKOUT0B, CLKOUT1, CLKOUT1B, CLKOUT2, CLKOUT2B,
            CLKOUT3, CLKOUT3B, CLKOUT4, CLKOUT5, CLKOUT6} = {2'b0, 12'b0};
endmodule

module xpm_cdc_single #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                        parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1) (
    input logic src_clk, input logic src_in, input logic dest_clk, output logic dest_out);
    logic [DEST_SYNC_FF-1:0] sr;
    always_ff @(posedge dest_clk) sr <= {sr[DEST_SYNC_FF-2:0], src_in};
    assign dest_out = sr[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_array_single #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                              parameter int SIM_ASSERT_CHK = 0, parameter int SRC_INPUT_REG = 1,
                              parameter int WIDTH = 2) (
    input logic src_clk, input logic [WIDTH-1:0] src_in, input logic dest_clk, output logic [WIDTH-1:0] dest_out);
    logic [WIDTH-1:0] sr [DEST_SYNC_FF];
    always_ff @(posedge dest_clk) begin
        sr[0] <= src_in;
        for (int i = 1; i < DEST_SYNC_FF; i++) sr[i] <= sr[i-1];
    end
    assign dest_out = sr[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_async_rst #(parameter int DEST_SYNC_FF = 4, parameter int INIT_SYNC_FF = 0,
                           parameter int RST_ACTIVE_HIGH = 0) (
    input logic src_arst, input logic dest_clk, output logic dest_arst);
    logic [DEST_SYNC_FF-1:0] sr;
    always_ff @(posedge dest_clk) begin
        if (src_arst) sr <= '1;
        else sr <= {sr[DEST_SYNC_FF-2:0], 1'b0};
    end
    assign dest_arst = sr[DEST_SYNC_FF-1];
endmodule
`endif
