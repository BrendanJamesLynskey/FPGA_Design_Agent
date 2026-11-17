`timescale 1ns/1ps
// tb_pcs_mac.sv: bench top for brief 96's PCS and MAC: transmit chain (mac64_tx -> pcs_tx, or XGMII words driven directly) and receive
// chain (pcs_rx -> mac64_rx), joined by the cocotb bench, which carries the 64-bit GT words between them through a bit-level channel.
module tb_pcs_mac (
    input  logic        clk_tx, rst_tx, direct,
    input  logic [63:0] dx_d,
    input  logic [7:0]  dx_c,
    input  logic        s_valid, s_last, s_poison,
    input  logic [63:0] s_data,
    input  logic [2:0]  s_nb1,
    output logic        s_ready, sop, eop, underrun, adv,
    output logic [63:0] gt_tx_d,
    input  logic        clk_rx, rst_rx,
    input  logic [63:0] gt_rx_d,
    output logic        x_v, lock, ev_sh_err, ev_type_err, ev_os, ev_slip, ev_loss, ev_lock,
    output logic [63:0] x_d,
    output logic [7:0]  x_c,
    output logic        m_v, m_sof, m_end, m_fcs_ok, m_err, rx_sop,
    output logic [63:0] m_d,
    output logic [3:0]  m_nb,
    output logic [15:0] m_len,
    output logic [63:0] mx_d,
    output logic [7:0]  mx_c
);
    logic [63:0] xm_d, p_d;
    logic [7:0]  xm_c, p_c;
    mac64_tx u_mt (.clk(clk_tx), .rst(rst_tx), .adv, .s_valid, .s_data, .s_last, .s_nb1, .s_poison, .s_ready,
                   .x_d(xm_d), .x_c(xm_c), .sop, .eop, .underrun);
    assign p_d = direct ? dx_d : xm_d;
    assign p_c = direct ? dx_c : xm_c;
    assign mx_d = xm_d;
    assign mx_c = xm_c;
    pcs_tx u_pt (.clk(clk_tx), .rst(rst_tx), .x_d(p_d), .x_c(p_c), .adv, .gt_d(gt_tx_d));
    pcs_rx u_pr (.clk(clk_rx), .rst(rst_rx), .gt_d(gt_rx_d), .x_v, .x_d, .x_c, .lock, .ev_sh_err, .ev_type_err, .ev_os, .ev_slip, .ev_loss, .ev_lock);
    mac64_rx u_mr (.clk(clk_rx), .rst(rst_rx), .x_v, .x_d, .x_c, .m_v, .m_d, .m_sof, .m_nb, .m_end, .m_fcs_ok, .m_len, .m_err, .rx_sop);
endmodule
