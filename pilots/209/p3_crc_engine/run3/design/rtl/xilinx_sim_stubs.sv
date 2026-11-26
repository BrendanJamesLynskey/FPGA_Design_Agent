// Simulation-only stand-ins; Vivado supplies the real primitives in synthesis.
`ifndef SYNTHESIS
/* verilator lint_off DECLFILENAME */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off UNUSEDSIGNAL */
module BUFG (input logic I, output logic O);
    assign O = I;
endmodule

module MMCME4_BASE #(
    parameter real CLKIN1_PERIOD = 10.0, parameter real CLKFBOUT_MULT_F = 5.0,
    parameter int DIVCLK_DIVIDE = 1, parameter real CLKOUT0_DIVIDE_F = 1.0
) (
    input  logic CLKIN1, CLKFBIN, PWRDWN, RST,
    output logic CLKFBOUT, CLKOUT0, LOCKED,
    output logic CLKFBOUTB, CLKOUT0B, CLKOUT1, CLKOUT1B, CLKOUT2, CLKOUT2B,
    output logic CLKOUT3, CLKOUT3B, CLKOUT4, CLKOUT5, CLKOUT6
);
    assign CLKFBOUT = CLKIN1; assign CLKOUT0 = CLKIN1; assign LOCKED = 1'b1;
    assign {CLKFBOUTB, CLKOUT0B, CLKOUT1, CLKOUT1B, CLKOUT2, CLKOUT2B, CLKOUT3, CLKOUT3B,
            CLKOUT4, CLKOUT5, CLKOUT6} = '0;
endmodule

module xpm_cdc_single #(parameter int DEST_SYNC_FF = 4, INIT_SYNC_FF = 0, SIM_ASSERT_CHK = 0, SRC_INPUT_REG = 1) (
    input logic src_clk, src_in, dest_clk, output logic dest_out);
    logic [DEST_SYNC_FF-1:0] s;
    always_ff @(posedge dest_clk) s <= {s[DEST_SYNC_FF-2:0], src_in};
    assign dest_out = s[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_array_single #(parameter int DEST_SYNC_FF = 4, INIT_SYNC_FF = 0, SIM_ASSERT_CHK = 0,
                              SRC_INPUT_REG = 1, WIDTH = 2) (
    input logic src_clk, input logic [WIDTH-1:0] src_in, input logic dest_clk,
    output logic [WIDTH-1:0] dest_out);
    logic [WIDTH-1:0] s [DEST_SYNC_FF];
    always_ff @(posedge dest_clk) begin
        s[0] <= src_in;
        for (int i = 1; i < DEST_SYNC_FF; i++) s[i] <= s[i-1];
    end
    assign dest_out = s[DEST_SYNC_FF-1];
endmodule

module xpm_cdc_async_rst #(parameter int DEST_SYNC_FF = 4, INIT_SYNC_FF = 0, RST_ACTIVE_HIGH = 0) (
    input logic src_arst, dest_clk, output logic dest_arst);
    logic [DEST_SYNC_FF-1:0] s;
    logic a;
    assign a = (src_arst == (RST_ACTIVE_HIGH != 0));
    always_ff @(posedge dest_clk) begin
        if (a) s <= '1;
        else   s <= {s[DEST_SYNC_FF-2:0], 1'b0};
    end
    assign dest_arst = s[DEST_SYNC_FF-1];
endmodule

module BSCANE2 #(parameter int JTAG_CHAIN = 1) (
    output logic TCK, TDI, SEL, SHIFT, CAPTURE, UPDATE, DRCK, RESET, RUNTEST, TMS, input logic TDO);
    assign {TCK, TDI, SEL, SHIFT, CAPTURE, UPDATE, DRCK, RESET, RUNTEST, TMS} = '0;
endmodule

module USR_ACCESSE2 (output logic CFGCLK, output logic [31:0] DATA, output logic DATAVALID);
    assign CFGCLK = 1'b0; assign DATA = 32'h0; assign DATAVALID = 1'b0;
endmodule
`endif
