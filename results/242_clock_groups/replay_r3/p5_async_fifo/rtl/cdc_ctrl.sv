// cdc_ctrl: the control and result crossings between clk_wr and clk_rd, all through XPM primitives.
//   ctl  clk_wr -> clk_rd : SLOW_READ level, CLEAR level, INJECT toggle, SNAPSHOT toggle (quasi-static)
//   err  clk_rd -> clk_wr : sticky error level
//   res  clk_rd -> clk_wr : 96-bit reader counter set, coherent by four-phase handshake
// No registers of its own.
module cdc_ctrl (
    input  logic        clk_wr,
    input  logic        clk_rd,
    input  logic [3:0]  ctl_wr,
    output logic [3:0]  ctl_rd,
    input  logic        err_rd,
    output logic        err_wr,
    input  logic [95:0] res_rd,
    input  logic        res_send,
    output logic        res_rcv,
    output logic [95:0] res_wr,
    output logic        res_req
);
    xpm_cdc_array_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(0), .WIDTH(4)) u_ctl (
        .src_clk(clk_wr), .src_in(ctl_wr), .dest_clk(clk_rd), .dest_out(ctl_rd));

    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(0)) u_err (
        .src_clk(clk_rd), .src_in(err_rd), .dest_clk(clk_wr), .dest_out(err_wr));

    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_SYNC_FF(2), .WIDTH(96)) u_hs (
        .src_clk(clk_rd), .src_in(res_rd), .src_send(res_send), .src_rcv(res_rcv),
        .dest_clk(clk_wr), .dest_out(res_wr), .dest_req(res_req), .dest_ack(1'b0));
endmodule
