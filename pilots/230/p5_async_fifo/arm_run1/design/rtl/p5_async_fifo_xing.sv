// Control, snapshot and status clock crossings of the soak core (all through XPM CDC primitives).
/* verilator lint_off DECLFILENAME */
module top #(
    parameter int W = 32
) (
    input  logic             clk_wr,
    input  logic             clk_rd,
    input  logic [2:0]       ctl_wr,     // {clr, inj, slow} in clk_wr
    output logic [2:0]       ctl_rd,
    input  logic             snap_t,     // snapshot toggle in clk_wr
    output logic             snap_rd,
    input  logic [1:0]       back_rd,    // {inj_done, err_flag} in clk_rd
    output logic [1:0]       back_wr,
    input  logic [3*W-1:0]   hs_in,
    input  logic             hs_send,
    output logic             hs_rcv,
    output logic             hs_req,
    output logic [3*W-1:0]   hs_out
);
    xpm_cdc_array_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0), .WIDTH(3)) u_ctl (
        .src_clk(clk_wr), .src_in(ctl_wr), .dest_clk(clk_rd), .dest_out(ctl_rd));
    xpm_cdc_array_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0), .WIDTH(1)) u_snap (
        .src_clk(clk_wr), .src_in(snap_t), .dest_clk(clk_rd), .dest_out(snap_rd));
    xpm_cdc_array_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(1), .WIDTH(2)) u_back (
        .src_clk(clk_rd), .src_in(back_rd), .dest_clk(clk_wr), .dest_out(back_wr));
    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_SYNC_FF(2),
                        .WIDTH(3*W)) u_hs (
        .src_clk(clk_rd), .src_in(hs_in), .src_send(hs_send), .src_rcv(hs_rcv),
        .dest_clk(clk_wr), .dest_req(hs_req), .dest_ack(1'b0), .dest_out(hs_out));
endmodule
