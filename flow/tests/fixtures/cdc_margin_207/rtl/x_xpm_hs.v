// x_xpm_hs: one xpm_cdc_handshake (16 bits, DEST_SYNC_FF 3) and one xpm_cdc_gray (8 bits), clk_a 100 MHz to clk_b 156.25 MHz.
// Brief 207 finding 5: which max delay and bus skew does our flow (flow/xpm_cdc.tcl) apply, against AMD's own template?
module x_xpm_hs (
    input  wire        clk_a, input wire clk_b,
    input  wire [15:0] d_a, input wire send_a, output wire rcv_a,
    output wire [15:0] d_b, output wire req_b, input wire ack_b,
    input  wire [7:0]  g_a, output wire [7:0] g_b
);
    xpm_cdc_handshake #(.DEST_EXT_HSK(1), .DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_SYNC_FF(3), .WIDTH(16))
    u_hs (.src_clk(clk_a), .src_in(d_a), .src_send(send_a), .src_rcv(rcv_a),
          .dest_clk(clk_b), .dest_out(d_b), .dest_req(req_b), .dest_ack(ack_b));
    xpm_cdc_gray #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .SIM_ASSERT_CHK(1), .SIM_LOSSLESS_GRAY_CHK(0), .WIDTH(8))
    u_gray (.src_clk(clk_a), .src_in_bin(g_a), .dest_clk(clk_b), .dest_out_bin(g_b));
endmodule
