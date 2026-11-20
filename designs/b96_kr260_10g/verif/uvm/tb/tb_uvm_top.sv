`timescale 1ns/1ps
// tb_uvm_top.sv: the hardware top of the b96 PCS and MAC UVM bench (brief 112): mac64_tx -> pcs_tx -> line_channel -> pcs_rx -> mac64_rx on one
// clock, with the direct XGMII injection mux in front of pcs_tx and the interfaces the agents drive and watch. No GT model: the GTH is replaced by
// the channel (the real GTHE4 model is refused by the Basic simulator, results/56a_serdes/xsim_refusal.txt).
module tb_uvm_top;
    import uvm_pkg::*;
    import pcs_mac_uvm_pkg::*;
    `include "uvm_macros.svh"

    logic clk = 1'b0;
    always #3.103 clk = ~clk;

    sys_if  sys  (clk);
    usr_if  usr  (clk);
    xg_if   xg   (clk);
    line_if line (clk);
    rx_if   rxi  (clk);

    logic        rst_rx;
    logic [63:0] xm_d, p_d, gt_tx_d, gt_rx_d, x_d, m_d;
    logic [7:0]  xm_c, p_c, x_c;
    logic        adv, s_ready, sop, eop, underrun;
    logic        x_v, x_os, lock, ev_sh_err, ev_type_err, ev_os, ev_slip, ev_loss, ev_lock;
    logic        m_v, m_sof, m_end, m_fcs_ok, m_err, rx_sop;
    logic [3:0]  m_nb;
    logic [15:0] m_len;

    assign rst_rx = sys.rst_rx_sys | line.rst_rx_req;
    assign p_d = xg.direct ? xg.dx_d : xm_d;
    assign p_c = xg.direct ? xg.dx_c : xm_c;

    mac64_tx u_mt (.clk, .rst(sys.rst_tx), .adv, .s_valid(usr.s_valid), .s_data(usr.s_data), .s_last(usr.s_last), .s_nb1(usr.s_nb1),
                   .s_poison(usr.s_poison), .s_ready, .x_d(xm_d), .x_c(xm_c), .sop, .eop, .underrun);
    pcs_tx  u_pt (.clk, .rst(sys.rst_tx), .x_d(p_d), .x_c(p_c), .adv, .gt_d(gt_tx_d));
    line_channel u_ch (.clk, .rst(sys.rst_tx), .line_mode(sys.line_mode), .init_off(sys.init_off), .tx_word(gt_tx_d), .drv_word(line.drv_word),
                       .drv_valid(line.drv_valid), .drv_first(line.drv_first), .flip_mask(line.flip_mask), .hdr_load(line.hdr_load),
                       .hdr_cnt(line.hdr_cnt), .hdr_skip(line.hdr_skip), .slip_ins(line.slip_ins), .slip_del(line.slip_del), .out_word(gt_rx_d));
    pcs_rx  u_pr (.clk, .rst(rst_rx), .gt_d(gt_rx_d), .x_v, .x_d, .x_c, .x_os, .lock, .ev_sh_err, .ev_type_err, .ev_os, .ev_slip, .ev_loss, .ev_lock);
    mac64_rx u_mr (.clk, .rst(rst_rx), .lock_i(lock), .x_v, .x_d, .x_c, .m_v, .m_d, .m_sof, .m_nb, .m_end, .m_fcs_ok, .m_len, .m_err, .rx_sop);

    // observation nets into the interfaces
    assign usr.s_ready = s_ready; assign usr.sop = sop; assign usr.eop = eop; assign usr.underrun = underrun; assign usr.adv = adv;
    assign xg.xm_d = xm_d; assign xg.xm_c = xm_c; assign xg.p_d = p_d; assign xg.p_c = p_c; assign xg.adv = adv; assign xg.rst_tx = sys.rst_tx;
    assign line.gt_tx_d = gt_tx_d; assign line.gt_rx_d = gt_rx_d; assign line.rst_rx = rst_rx;
    assign rxi.rst_rx = rst_rx; assign rxi.lock = lock; assign rxi.x_v = x_v; assign rxi.x_os = x_os; assign rxi.x_d = x_d; assign rxi.x_c = x_c;
    assign rxi.ev_sh_err = ev_sh_err; assign rxi.ev_type_err = ev_type_err; assign rxi.ev_os = ev_os; assign rxi.ev_slip = ev_slip;
    assign rxi.ev_loss = ev_loss; assign rxi.ev_lock = ev_lock;
    assign rxi.m_v = m_v; assign rxi.m_sof = m_sof; assign rxi.m_end = m_end; assign rxi.m_fcs_ok = m_fcs_ok; assign rxi.m_err = m_err;
    assign rxi.rx_sop = rx_sop; assign rxi.m_d = m_d; assign rxi.m_nb = m_nb; assign rxi.m_len = m_len;

    initial begin
        uvm_config_db#(virtual sys_if)::set(null, "*", "sys_vif", sys);
        uvm_config_db#(virtual usr_if)::set(null, "*", "usr_vif", usr);
        uvm_config_db#(virtual xg_if)::set(null, "*", "xg_vif", xg);
        uvm_config_db#(virtual line_if)::set(null, "*", "line_vif", line);
        uvm_config_db#(virtual rx_if)::set(null, "*", "rx_vif", rxi);
        run_test();
    end
endmodule
