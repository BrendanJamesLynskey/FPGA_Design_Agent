// Proof stand-ins for the XPM clock-crossing macros: each is a plain wire (no clock, no delay), the same on both sides of the comparison, so
// the proof covers everything around the crossings; the crossings themselves are not tested by this proof.
module xpm_cdc_single #(parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0, parameter integer SIM_ASSERT_CHK = 0, parameter integer SRC_INPUT_REG = 1)
  (input wire src_clk, input wire src_in, input wire dest_clk, output wire dest_out);
  assign dest_out = src_in;
endmodule
module xpm_cdc_array_single #(parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0, parameter integer SIM_ASSERT_CHK = 0, parameter integer SRC_INPUT_REG = 1, parameter integer WIDTH = 2)
  (input wire src_clk, input wire [WIDTH-1:0] src_in, input wire dest_clk, output wire [WIDTH-1:0] dest_out);
  assign dest_out = src_in;
endmodule
module xpm_cdc_sync_rst #(parameter integer DEST_SYNC_FF = 4, parameter integer INIT = 1, parameter integer INIT_SYNC_FF = 0, parameter integer SIM_ASSERT_CHK = 0)
  (input wire src_rst, input wire dest_clk, output wire dest_rst);
  assign dest_rst = src_rst;
endmodule
module xpm_cdc_pulse #(parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0, parameter integer REG_OUTPUT = 0, parameter integer RST_USED = 1, parameter integer SIM_ASSERT_CHK = 0)
  (input wire src_clk, input wire src_pulse, input wire dest_clk, input wire src_rst, input wire dest_rst, output wire dest_pulse);
  assign dest_pulse = src_pulse;
endmodule
module xpm_cdc_gray #(parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0, parameter integer REG_OUTPUT = 0, parameter integer SIM_ASSERT_CHK = 0, parameter integer SIM_LOSSLESS_GRAY_CHK = 0, parameter integer WIDTH = 2)
  (input wire src_clk, input wire [WIDTH-1:0] src_in_bin, input wire dest_clk, output wire [WIDTH-1:0] dest_out_bin);
  assign dest_out_bin = src_in_bin;
endmodule
module xpm_cdc_handshake #(parameter integer DEST_EXT_HSK = 1, parameter integer DEST_SYNC_FF = 4, parameter integer INIT_SYNC_FF = 0, parameter integer SIM_ASSERT_CHK = 0, parameter integer SRC_SYNC_FF = 4, parameter integer WIDTH = 1)
  (input wire src_clk, input wire [WIDTH-1:0] src_in, input wire src_send, output wire src_rcv, input wire dest_clk, output wire [WIDTH-1:0] dest_out, output wire dest_req, input wire dest_ack);
  assign dest_out = src_in; assign dest_req = src_send; assign src_rcv = dest_ack;
endmodule
