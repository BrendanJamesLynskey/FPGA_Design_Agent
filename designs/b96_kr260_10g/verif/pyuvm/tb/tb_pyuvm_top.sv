`timescale 1ns/1ps
// tb_pyuvm_top.sv: the hardware top of the pyuvm bench for the b96 PCS and MAC (brief 123). The same chain as brief 112's tb_uvm_top.sv, on one clock:
// mac64_tx -> (XGMII injection mux) -> pcs_tx ... pcs_rx -> mac64_rx. The bit-level channel between TXDATA and RXDATA is NOT in the hardware here: it is
// Python (pcs_mac_pyuvm/channel.py), so gt_rx_d and the two resets are plain inputs driven by the line agent. Unlike sim/tb_pcs_mac.sv (brief 96's top) this one
// has a single clock and exposes pcs_rx's x_os.
module tb_pyuvm_top (
    input  logic        clk, rst_tx, rst_rx, direct,
    input  logic [63:0] dx_d,
    input  logic [7:0]  dx_c,
    input  logic        s_valid, s_last, s_poison,
    input  logic [63:0] s_data,
    input  logic [2:0]  s_nb1,
    output logic        s_ready, sop, eop, underrun, adv,
    output logic [63:0] gt_tx_d, mx_d, p_d,
    output logic [7:0]  mx_c, p_c,
    input  logic [63:0] gt_rx_d,
    output logic        x_v, x_os, lock, ev_sh_err, ev_type_err, ev_os, ev_slip, ev_loss, ev_lock,
    output logic [63:0] x_d,
    output logic [7:0]  x_c,
    output logic        m_v, m_sof, m_end, m_fcs_ok, m_err, rx_sop,
    output logic [63:0] m_d,
    output logic [3:0]  m_nb,
    output logic [15:0] m_len
);
    logic [63:0] xm_d;
    logic [7:0]  xm_c;
    mac64_tx u_mt (.clk, .rst(rst_tx), .adv, .s_valid, .s_data, .s_last, .s_nb1, .s_poison, .s_ready, .x_d(xm_d), .x_c(xm_c), .sop, .eop, .underrun);
    assign p_d = direct ? dx_d : xm_d;
    assign p_c = direct ? dx_c : xm_c;
    assign mx_d = xm_d;
    assign mx_c = xm_c;
    pcs_tx u_pt (.clk, .rst(rst_tx), .x_d(p_d), .x_c(p_c), .adv, .gt_d(gt_tx_d));
    pcs_rx u_pr (.clk, .rst(rst_rx), .gt_d(gt_rx_d), .x_v, .x_d, .x_c, .x_os, .lock, .ev_sh_err, .ev_type_err, .ev_os, .ev_slip, .ev_loss, .ev_lock);
    mac64_rx u_mr (.clk, .rst(rst_rx), .lock_i(lock), .x_v, .x_d, .x_c, .m_v, .m_d, .m_sof, .m_nb, .m_end, .m_fcs_ok, .m_len, .m_err, .rx_sop);
endmodule
