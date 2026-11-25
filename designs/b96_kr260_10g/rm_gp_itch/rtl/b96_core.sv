// b96_core.sv (variant rm_gp_itch of brief 127: RATE_MATCH = 1 only; the ITCH path (itch_path) between the receive MAC and the transmit multiplexer, its host registers 0x300 to 0x37C
// and its counter window 0x400 to 0x57C, FEATURES bit 7; the RATE_MATCH = 0 receive path, the 96D eye scan and the 96F bypass are not in this variant): everything of brief 96's KR260 10GBASE-R design except the board pins' buffers, the clock generator, the SYSMON and the JTAG
// front end (kr260_10g_top): the GT Wizard core carrying the line (the one of brief 56A: RAW, 64-bit user data, QPLL0, 156.25 MHz
// reference), our own PCS and MAC in each user-clock domain (tx_path, rx_path), the host register block (docs/register_map.md is the
// specification) and the crossings between the three clock domains:
//   clk (free-running 100 MHz: registers, reset helper) | tx_clk (TXUSRCLK2, 161.1328125 MHz) | rx_clk (RXUSRCLK2, recovered)
// Crossings: configuration, counters and status by hs_vec (XPM request/acknowledge handshake, always coherent); command pulses by xpm_cdc_pulse.
// With RATE_MATCH = 1 (brief 96C) the receive path's blocks cross from rx_clk to tx_clk once, through the elastic buffer rate_match (idle insertion and deletion
// between frames keep the +-100 ppm difference of a real link from ever corrupting a frame); the MAC, the trading path and the order
// path then share the transmit user clock, so the decision reaches the order logic with no further crossing. With RATE_MATCH = 0 (the default) the receive
// path is the one of main 6909e43f (rx_path_legacy: pulse and bus crossings, no elastic buffer; board-proven by brief 97C).
module b96_core #(
    parameter logic [31:0] BUILD_STAMP = 32'h0,
    parameter bit          NEAR_END    = 1'b0,    // reset value of the loopback field: 1 = near-end PMA loopback (variant a)
    parameter bit          TRADE       = 1'b1,    // 1 = the mock trading path is armed to be enabled (variant b); reported in FEATURES
    parameter bit          RATE_MATCH  = 1'b0,    // 1 = brief 96C's elastic buffer on the receive path; 0 = the receive path of main 6909e43f (brief 97C); reported in FEATURES bit 3
    parameter bit          EYESCAN     = 1'b0,    // 1 = brief 96D's DRP access, eye-scan point sequencer and TX drive registers (reported in FEATURES bit 4); 0 = none (the GT's DRP and drive ports are tied as before)
    parameter bit          GO_REG      = 1'b1,    // RATE_MATCH = 0 only: REG_OUTPUT of the go-pulse crossing u_p_go (1 as on main; brief 97's latency variant all3 builds it 0)
    parameter bit          RM_DIRECT   = 1'b0,    // RM_OWN = 1 only (brief 96E): 1 = rate_match_gp with ENT_SYNC = 0 (direct read of the entry flops, build rm_gp_direct; fails report_cdc); 0 = ENT_SYNC = 1 (the default)
    parameter bit          RM_OWN      = 1'b0     // RATE_MATCH = 1 only (brief 96E): 1 = our own gray-pointer elastic buffer (rate_match_gp.sv), 0 = the one on AMD's xpm_fifo_async (rate_match.sv); reported in FEATURES bit 5
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    input  logic        refclk,
    input  logic        rx_p,
    input  logic        rx_n,
    output logic        tx_p,
    output logic        tx_n,
    output logic        sfp_tx_disable,
    input  logic        sfp_mod_abs,
    input  logic        sfp_rx_los,
    input  logic        sfp_tx_fault,
    output logic        i2c_scl_low,
    output logic        i2c_sda_low,
    input  logic        i2c_scl_i,
    input  logic        i2c_sda_i,
    output logic        sm_en,
    output logic [7:0]  sm_addr,
    input  logic [15:0] sm_do,
    input  logic        sm_rdy,
    output logic [1:0]  led
);
    import b96_pkg::*;
    import itch_pkg2::*;
    localparam int NTXW = 26;
    localparam logic [31:0] ID = 32'h96A0_0001;

    // ---------------------------------------------------------------- registers (clk domain)
    logic [2:0]  loopback;
    logic        tx_disable, tx_pol, rx_pol, rx_lpm;
    logic [3:0]  rs_all, rs_txpll, rs_rxpll, rs_txdp, rs_rxdp;
    logic        p_clr, p_gen, p_snap, p_seq, tx_done_q, rx_done_q;
    logic [4:0]  ppm_step;
    logic        ppm_en, ppm_sel;
    logic [47:0] my_mac, venue_mac;
    logic [31:0] my_ip, venue_ip, thr, qty;
    logic [15:0] sport, port_feed, port_order, port_probe;
    logic        arm, kill, trade_en;
    logic [1:0]  gen_kind;
    logic [15:0] gen_len, gen_inst;
    logic [31:0] gen_price, gen_interval, gen_count;
    logic        i2c_scl_r, i2c_sda_r;
    logic [7:0]  sm_addr_r;
    logic        sm_valid;
    logic [15:0] sm_data;
    logic [CFGW-1:0] cfg;
    assign cfg = {gen_count, gen_interval, gen_price, gen_inst, gen_len, gen_kind, trade_en, kill, arm, qty, thr, port_probe, port_order,
                  port_feed, sport, venue_ip, my_ip, venue_mac, my_mac};

    // ---------------------------------------------------------------- the GT Wizard core
    logic        tx_pol_t, rx_pol_r;           // declared before the GT instance that uses them (xsim refuses the implicit declaration; brief 96E)
    logic        txusr2, rxusr2;
    logic        tx_done_t, rx_done_r, cdr_stable_c, pgood_c, cdrlock_c, txpmadone_c, rxpmadone_c, utx_act_t, urx_act_r;
    logic [63:0] tx_data, rx_data;
    logic        txpmadone, rxpmadone, tx_done, rx_done, cdr_stable, pgood, cdrlock;
    logic        wz_all, wz_txpll, wz_rxpll, wz_txdp, wz_rxdp;
    logic        wz_utx = 1'b1, wz_urx = 1'b1;
    always_ff @(posedge clk) begin
        wz_all   <= rst || (rs_all != 4'd0);
        wz_txpll <= (rs_txpll != 4'd0);
        wz_rxpll <= (rs_rxpll != 4'd0);
        wz_txdp  <= (rs_txdp != 4'd0);
        wz_rxdp  <= (rs_rxdp != 4'd0);
        wz_utx   <= ~txpmadone;
        wz_urx   <= ~rxpmadone;
    end
    logic [9:0]  drp_addr;
    logic [15:0] drp_di, drp_do;
    logic        drp_en, drp_we, drp_rdy;
    logic [4:0]  tx_diff, tx_pre, tx_post;
    logic        rx_dfelpm_rst;
    logic       txusr1, ppm_en_t, ppm_sel_t;
    logic [4:0] ppm_step_t;
    logic [1:0] txbuf_c;
    logic [2:0] rxbuf_c;
    gth_wiz u_gt (
        .gtwiz_userclk_tx_reset_in(wz_utx), .gtwiz_userclk_tx_srcclk_out(), .gtwiz_userclk_tx_usrclk_out(txusr1),
        .gtwiz_userclk_tx_usrclk2_out(txusr2), .gtwiz_userclk_tx_active_out(utx_act_t),
        .gtwiz_userclk_rx_reset_in(wz_urx), .gtwiz_userclk_rx_srcclk_out(), .gtwiz_userclk_rx_usrclk_out(),
        .gtwiz_userclk_rx_usrclk2_out(rxusr2), .gtwiz_userclk_rx_active_out(urx_act_r),
        .gtwiz_reset_clk_freerun_in(clk), .gtwiz_reset_all_in(wz_all),
        .gtwiz_reset_tx_pll_and_datapath_in(wz_txpll), .gtwiz_reset_tx_datapath_in(wz_txdp),
        .gtwiz_reset_rx_pll_and_datapath_in(wz_rxpll), .gtwiz_reset_rx_datapath_in(wz_rxdp),
        .gtwiz_reset_rx_cdr_stable_out(cdr_stable_c), .gtwiz_reset_tx_done_out(tx_done_t),
        .gtwiz_reset_rx_done_out(rx_done_r),
        .gtwiz_userdata_tx_in(tx_data), .gtwiz_userdata_rx_out(rx_data),
        .gtrefclk00_in(refclk), .qpll0outclk_out(), .qpll0outrefclk_out(),
        .drpaddr_in(drp_addr), .drpclk_in(clk), .drpdi_in(drp_di), .drpen_in(drp_en), .drpwe_in(drp_we),
        .drpdo_out(drp_do), .drprdy_out(drp_rdy),
        .eyescanreset_in(1'b0), .eyescantrigger_in(1'b0), .eyescandataerror_out(),
        .gthrxn_in(rx_n), .gthrxp_in(rx_p), .gthtxn_out(tx_n), .gthtxp_out(tx_p),
        .loopback_in(loopback), .rxcdrhold_in(1'b0), .rxdfelpmreset_in(rx_dfelpm_rst), .rxlpmen_in(rx_lpm),
        .rxpolarity_in(rx_pol_r), .rxprbscntreset_in(1'b0), .rxprbssel_in(4'd0),
        .txdiffctrl_in(tx_diff), .txelecidle_in(1'b0), .txpippmen_in(ppm_en_t), .txpippmsel_in(ppm_sel_t),
        .txpippmstepsize_in(ppm_step_t), .txpolarity_in(tx_pol_t), .txpostcursor_in(tx_post), .txprbsforceerr_in(1'b0),
        .txprbssel_in(4'd0), .txprecursor_in(tx_pre),
        .gtpowergood_out(pgood_c), .rxcdrlock_out(cdrlock_c), .rxpmaresetdone_out(rxpmadone_c),
        .rxprbserr_out(), .rxprbslocked_out(), .txpmaresetdone_out(txpmadone_c),
        .txbufstatus_out(txbuf_c), .rxbufstatus_out(rxbuf_c));
    // the TX phase-interpolator ppm controller's controls (UG576 Table 3-33: TXUSRCLK domain, and TXUSRCLK (not TXUSRCLK2) when the internal data width is below the user width, as here): one bus into TXUSRCLK
    xpm_cdc_array_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(1), .WIDTH(7)) u_c_ppm (.src_clk(clk), .src_in({ppm_sel, ppm_en, ppm_step}), .dest_clk(txusr1), .dest_out({ppm_sel_t, ppm_en_t, ppm_step_t}));
    xpm_cdc_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(1)) u_c_tp (.src_clk(clk), .src_in(tx_pol), .dest_clk(txusr2), .dest_out(tx_pol_t));
    xpm_cdc_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(1)) u_c_rp (.src_clk(clk), .src_in(rx_pol), .dest_clk(rxusr2), .dest_out(rx_pol_r));

    // levels from the GT into clk (as 56A)
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(0)) u_s_tx (.src_clk(txusr2), .src_in(tx_done_t), .dest_clk(clk), .dest_out(tx_done));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(0)) u_s_rx (.src_clk(rxusr2), .src_in(rx_done_r), .dest_clk(clk), .dest_out(rx_done));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(0)) u_s_cs (.src_clk(1'b0), .src_in(cdr_stable_c), .dest_clk(clk), .dest_out(cdr_stable));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(0)) u_s_pg (.src_clk(1'b0), .src_in(pgood_c), .dest_clk(clk), .dest_out(pgood));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(0)) u_s_cl (.src_clk(1'b0), .src_in(cdrlock_c), .dest_clk(clk), .dest_out(cdrlock));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(0)) u_s_tp (.src_clk(1'b0), .src_in(txpmadone_c), .dest_clk(clk), .dest_out(txpmadone));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(0)) u_s_rp (.src_clk(1'b0), .src_in(rxpmadone_c), .dest_clk(clk), .dest_out(rxpmadone));
    logic [1:0] txbuf;
    logic [2:0] rxbuf;
    logic [1:0] txb_seen;
    logic [2:0] rxb_seen;
    xpm_cdc_array_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(0), .WIDTH(5)) u_s_bf (.src_clk(1'b0), .src_in({rxbuf_c, txbuf_c}), .dest_clk(clk), .dest_out({rxbuf, txbuf}));
    logic pcs_lock_rx, pcs_lock, mod_abs_c, rx_los_c, tx_fault_c, scl_c, sda_c;
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(1)) u_s_pl (.src_clk(rxusr2), .src_in(pcs_lock_rx), .dest_clk(clk), .dest_out(pcs_lock));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(0)) u_s_ma (.src_clk(1'b0), .src_in(sfp_mod_abs), .dest_clk(clk), .dest_out(mod_abs_c));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(0)) u_s_lo (.src_clk(1'b0), .src_in(sfp_rx_los), .dest_clk(clk), .dest_out(rx_los_c));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(0)) u_s_tf (.src_clk(1'b0), .src_in(sfp_tx_fault), .dest_clk(clk), .dest_out(tx_fault_c));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(0)) u_s_sc (.src_clk(1'b0), .src_in(i2c_scl_i), .dest_clk(clk), .dest_out(scl_c));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(1), .SRC_INPUT_REG(0)) u_s_sd (.src_clk(1'b0), .src_in(i2c_sda_i), .dest_clk(clk), .dest_out(sda_c));

    // ---------------------------------------------------------------- the two paths and their crossings
    // RATE_MATCH = 1 (brief 96C): the receive path's blocks cross from rx_clk to tx_clk once, through the elastic buffer rate_match; the MAC, the trading path and
    // the order path then share the transmit user clock. RATE_MATCH = 0 (the default): the receive path of main 6909e43f (brief 97C), unchanged: the MAC and the
    // trading path run in rx_clk and the decision crosses to tx_clk by pulses and a quasi-static bus. Both fill the same register map; the 96C-only words
    // (rate-match counters RXV18..RXV26, frequency counter RXV27/28) read 0 when RATE_MATCH = 0.
    logic [CFGW-1:0] cfg_tx;
    hs_vec #(.W(CFGW)) u_cfg_tx (.src_clk(clk), .src_vec(cfg), .dst_clk(txusr2), .dst_vec(cfg_tx));
    logic clr_tx, clr_rx, gen_tx, seq_tx;
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(1)) u_p_ct (.src_clk(clk), .src_pulse(p_clr), .src_rst(1'b0), .dest_clk(txusr2), .dest_pulse(clr_tx), .dest_rst(1'b0));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(1)) u_p_cr (.src_clk(clk), .src_pulse(p_clr), .src_rst(1'b0), .dest_clk(rxusr2), .dest_pulse(clr_rx), .dest_rst(1'b0));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(1)) u_p_st (.src_clk(clk), .src_pulse(p_seq), .src_rst(1'b0), .dest_clk(txusr2), .dest_pulse(seq_tx), .dest_rst(1'b0));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(1)) u_p_gt (.src_clk(clk), .src_pulse(p_gen), .src_rst(1'b0), .dest_clk(txusr2), .dest_pulse(gen_tx), .dest_rst(1'b0));

    // ---------------------------------------------------------------- brief 127: the ITCH path's registers and vectors
    // CFG2 (host -> core clock) is the register words below, STAT2 (core clock -> host) the counters and stamps of itch_path; both are coherent copies by hs_vec like cfg and the status vectors.
    logic [31:0] c2 [NCW];
    logic [31:0] c2s [NCW];                         // brief 188: staged copies of the limit words (host writes land here; one IT_CMD COMMIT copies them all to c2 in one clock)
    function automatic logic is_staged(input int w);
        return w == C_THR || w == C_QTY || w == C_MAXQTY || w == C_MAXPOS || w == C_BAND || w == C_PXOFF || w == C_REFPX || w == C_REFAGE;
    endfunction
    logic lim_pending;
    always_comb begin
        lim_pending = 1'b0;
        for (int i = 0; i < NCW; i++) if (is_staged(i) && c2s[i] != c2[i]) lim_pending = 1'b1;
    end
    logic [7:0]  c2_cmd_seq, c2_rpw_seq, c2_tcpf_seq;
    logic [15:0] c2_cmd_bits;
    logic [32*NCW-1:0] cfg2_vec, cfg2_tx;
    logic [32*NSW-1:0] stat2_t, stat2_live, stat2_snap;
    logic        i_m_v, i_m_sof, i_m_end, i_m_fcs, i_m_err, i_o_v, i_o_sof, i_o_eof, i_o_poison, i_o_unres, i_fcs_poison, i_rp_start, i_rp_stop, i_wr_we;
    logic [63:0] i_m_d, i_o_d, i_wr_data;
    logic [15:0] i_m_len, i_rp_loops;
    logic [7:0]  i_o_keep, i_wr_addr;
    logic [31:0] i_ts, t_rp_frames, t_rp_err, t_n_ofl;
    logic        t_ord_start, t_ord_drop, t_ord_end, t_ord_end_seg, t_ord_end_unres, t_ord_end_fcs, t_ord_end_ofl, t_ord_sop, t_ord_busy, t_rp_busy;
    always_comb begin
        for (int i = 0; i < NCW; i++) cfg2_vec[32*i +: 32] = c2[i];
        cfg2_vec[32*C_CMD +: 32]   = {8'd0, c2_cmd_seq, c2_cmd_bits};
        cfg2_vec[32*C_RPW +: 32]   = {8'd0, c2_rpw_seq, 8'd0, c2[C_RPW][7:0]};
        cfg2_vec[32*C_TCPFA +: 32] = {8'd0, c2_tcpf_seq, 3'd0, c2[C_TCPFA][12:8], 3'd0, c2[C_TCPFA][4:0]};
    end
    hs_vec #(.W(32 * NCW)) u_cfg2 (.src_clk(clk), .src_vec(cfg2_vec), .dst_clk(txusr2), .dst_vec(cfg2_tx));

    logic [32 * NRXW - 1:0] rx_live;
    logic [32 * NTXW - 1:0] tx_vec_t, tx_live;
    if (1'b1) begin : g_rm
        logic        r_fire, r_sop, r_feed, r_order, r_probe, r_verdict_v, r_verdict_bad;
        logic [15:0] r_inst;
        logic [31:0] r_price, r_qty, r_seq, r_verdict_seq;
        logic [32 * NRXV_W - 1:0] rxw_t, rxw_live;
        logic [32 * NRXV_C - 1:0] rxc_t, rxc_live;
        rx_path #(.RM_OWN(RM_OWN), .RM_DIRECT(RM_DIRECT)) u_rx (.clk(rxusr2), .rst(!rx_done_r), .clk_c(txusr2), .rst_c(!tx_done_t), .cfg(cfg_tx), .clr_w(clr_rx), .clr_c(clr_tx), .seq_c(seq_tx), .gt_d(rx_data),
            .fire(r_fire), .o_inst(r_inst), .o_price(r_price), .o_qty(r_qty), .o_seq(r_seq), .verdict_v(r_verdict_v), .verdict_bad(r_verdict_bad),
            .verdict_seq(r_verdict_seq), .rx_sop(r_sop), .cls_feed(r_feed), .cls_order(r_order), .cls_probe(r_probe), .lock(pcs_lock_rx),
            .rx_vec_w(rxw_t), .rx_vec_c(rxc_t),
            .m_v_o(i_m_v), .m_sof_o(i_m_sof), .m_end_o(i_m_end), .m_fcs_ok_o(i_m_fcs), .m_err_o(i_m_err), .m_d_o(i_m_d), .m_len_o(i_m_len));
        tx_path #(.NTXW(NTXW)) u_tx (.clk(txusr2), .rst(!tx_done_t), .cfg(cfg_tx), .clr_p(clr_tx), .seq_p(seq_tx), .gen_go_p(gen_tx), .go_p(r_fire), .go_inst(r_inst), .go_price(r_price),
            .go_qty(r_qty), .go_seq(r_seq), .verdict_v(r_verdict_v), .verdict_bad(r_verdict_bad), .verdict_seq(r_verdict_seq), .rx_sop_p(r_sop), .rx_feed_p(r_feed), .rx_order_p(r_order),
            .rx_probe_p(r_probe), .gt_d(tx_data), .tx_vec(tx_vec_t),
            .ts_o(i_ts), .i_o_v(i_o_v), .i_o_d(i_o_d), .i_o_sof(i_o_sof), .i_o_eof(i_o_eof), .i_o_keep(i_o_keep), .i_o_poison(i_o_poison), .i_o_unres(i_o_unres),
            .i_fcs_poison(i_fcs_poison), .i_rp_start(i_rp_start), .i_rp_stop(i_rp_stop), .i_rp_loops(i_rp_loops), .i_wr_we(i_wr_we), .i_wr_addr(i_wr_addr), .i_wr_data(i_wr_data),
            .ord_start(t_ord_start), .ord_drop(t_ord_drop), .ord_end(t_ord_end), .ord_end_seg(t_ord_end_seg), .ord_end_unres(t_ord_end_unres), .ord_end_fcs(t_ord_end_fcs),
            .ord_end_ofl(t_ord_end_ofl), .ord_sop(t_ord_sop), .ord_busy(t_ord_busy), .rp_frames(t_rp_frames), .rp_err(t_rp_err), .n_ofl(t_n_ofl), .rp_busy(t_rp_busy));
        itch_path u_ip (.clk(txusr2), .rst(!tx_done_t), .ts(i_ts), .cfg(cfg_tx), .rx_sop(r_sop), .m_v(i_m_v), .m_d(i_m_d), .m_sof(i_m_sof), .m_end(i_m_end), .m_fcs_ok(i_m_fcs), .m_len(i_m_len),
            .m_err(i_m_err), .cfg2(cfg2_tx), .stat2(stat2_t), .o_v(i_o_v), .o_d(i_o_d), .o_sof(i_o_sof), .o_eof(i_o_eof), .o_keep(i_o_keep), .o_poison(i_o_poison), .o_unres(i_o_unres),
            .fcs_poison(i_fcs_poison), .rp_start(i_rp_start), .rp_stop(i_rp_stop), .rp_loops(i_rp_loops), .wr_we(i_wr_we), .wr_addr(i_wr_addr), .wr_data(i_wr_data), .ord_start(t_ord_start), .ord_drop(t_ord_drop),
            .ord_end(t_ord_end), .ord_end_seg(t_ord_end_seg), .ord_end_unres(t_ord_end_unres), .ord_end_fcs(t_ord_end_fcs), .ord_end_ofl(t_ord_end_ofl), .ord_sop(t_ord_sop),
            .ord_busy(t_ord_busy), .rp_frames(t_rp_frames), .rp_err(t_rp_err), .n_ofl(t_n_ofl), .rp_busy(t_rp_busy));
        hs_vec #(.W(32 * NRXV_W)) u_rxv_w (.src_clk(rxusr2), .src_vec(rxw_t), .dst_clk(clk), .dst_vec(rxw_live));
        hs_vec #(.W(32 * NRXV_C)) u_rxv_c (.src_clk(txusr2), .src_vec(rxc_t), .dst_clk(clk), .dst_vec(rxc_live));
        for (genvar gi = 0; gi < NRXW; gi++) begin : g_rxv
            if (RXV_OWN_W[gi]) begin : w
                assign rx_live[32 * gi +: 32] = rxw_live[32 * rxv_pos(1'b1, gi) +: 32];
            end else begin : c
                assign rx_live[32 * gi +: 32] = rxc_live[32 * rxv_pos(1'b0, gi) +: 32];
            end
        end
    end
    // STAT2 is 96 words: xpm_cdc_handshake takes at most 1024 bits, so three coherent parts of 32 words (each part is one snapshot of the core clock; the three can be a few clocks apart)
    for (genvar gp = 0; gp < 3; gp++) begin : g_st2
        hs_vec #(.W(1024)) u_st2 (.src_clk(txusr2), .src_vec(stat2_t[1024 * gp +: 1024]), .dst_clk(clk), .dst_vec(stat2_live[1024 * gp +: 1024]));
    end
    hs_vec #(.W(32 * NTXW)) u_txv (.src_clk(txusr2), .src_vec(tx_vec_t), .dst_clk(clk), .dst_vec(tx_live));
    logic [32 * NRXW - 1:0] rx_snap;
    logic [32 * NTXW - 1:0] tx_snap;

    // ---------------------------------------------------------------- brief 96D: DRP access, eye-scan point sequencer, TX drive (EYESCAN = 1 only)
    // The DRP clock is clk (the GT's DRPCLK), so these registers need no crossing. TXDIFFCTRL, TXPRECURSOR, TXPOSTCURSOR and RXDFELPMRESET are asynchronous ports
    // of the GT (UG576 Tables 3-35 and 4-x): a static level from clk is fine. With EYESCAN = 0 they are the constants the design always drove.
    logic [9:0]  es_raw_addr;
    logic [15:0] es_raw_wd, es_raw_rd, es_res_err, es_res_samp, es_pt_count;
    logic        es_raw_rd_p, es_raw_wr_p, es_start_p, es_clr_p;
    logic        es_busy, es_done, es_ptmo, es_drptmo, es_rej;
    logic [3:0]  es_status;
    logic [7:0]  es_step;
    logic [11:0] pt_horz;
    logic [6:0]  pt_code;
    logic        pt_neg, pt_ut;
    logic [1:0]  pt_range;
    logic [4:0]  pt_pre_scale;
    logic [31:0] pt_tmo_clks;
    logic [4:0]  tx_diff_r, tx_pre_r, tx_post_r;
    logic        dfelpm_r;
    if (EYESCAN) begin : g_es
        es_ctrl u_es (.clk, .rst, .raw_addr(es_raw_addr), .raw_wdata(es_raw_wd), .raw_rd(es_raw_rd_p), .raw_wr(es_raw_wr_p), .pt_start(es_start_p), .clr_flags(es_clr_p),
            .pt_horz, .pt_vs_code(pt_code), .pt_vs_neg(pt_neg), .pt_vs_ut(pt_ut), .pt_vs_range(pt_range), .pt_prescale(pt_pre_scale), .pt_timeout(pt_tmo_clks),
            .raw_rdata(es_raw_rd), .busy(es_busy), .pt_done(es_done), .pt_tmo(es_ptmo), .drp_tmo(es_drptmo), .rejected(es_rej), .es_status, .step_o(es_step),
            .pt_count(es_pt_count), .res_err(es_res_err), .res_samp(es_res_samp), .drp_addr, .drp_di, .drp_en, .drp_we, .drp_do, .drp_rdy);
        assign tx_diff = tx_diff_r; assign tx_pre = tx_pre_r; assign tx_post = tx_post_r; assign rx_dfelpm_rst = dfelpm_r;
    end else begin : g_nes
        assign drp_addr = 10'd0; assign drp_di = 16'd0; assign drp_en = 1'b0; assign drp_we = 1'b0;
        assign tx_diff = 5'b11000; assign tx_pre = 5'd0; assign tx_post = 5'd0; assign rx_dfelpm_rst = 1'b0;
        assign es_raw_rd = '0; assign es_busy = 1'b0; assign es_done = 1'b0; assign es_ptmo = 1'b0; assign es_drptmo = 1'b0; assign es_rej = 1'b0; assign es_status = '0;
        assign es_step = '0; assign es_pt_count = '0; assign es_res_err = '0; assign es_res_samp = '0;
    end
    logic _unused_es;
    assign _unused_es = &{1'b0, drp_do, drp_rdy, es_raw_rd, es_busy, es_done, es_ptmo, es_drptmo, es_rej, es_status, es_step, es_pt_count, es_res_err, es_res_samp};

    // ---------------------------------------------------------------- host registers
    logic [31:0] rd;
    int          rx_i, tx_i, c2_wi, s2_i;
    assign c2_wi = (int'(h_addr) - 768) >> 2;
    assign s2_i  = (int'(h_addr) - 1024) >> 2;
    assign rx_i = (int'(h_addr) - 256) >> 2;
    assign tx_i = (int'(h_addr) - 512) >> 2;
    initial begin p_seq = 1'b0; tx_done_q = 1'b0; rx_done_q = 1'b0; end
    logic [7:0]  gen_dly;      // the run command is held back so the configuration (hs_vec, a few dozen clocks) has arrived first
    always_ff @(posedge clk) begin
        p_clr <= 1'b0; p_gen <= 1'b0; p_snap <= 1'b0;
        es_raw_rd_p <= 1'b0; es_raw_wr_p <= 1'b0; es_start_p <= 1'b0; es_clr_p <= 1'b0;
        // 97C: any restart of either side (a GT reset command, or either side's done level changing) restarts the order number on both sides
        tx_done_q <= tx_done; rx_done_q <= rx_done;
        p_seq <= (tx_done != tx_done_q) || (rx_done != rx_done_q) || (h_we && h_addr == 12'h010 && (h_wdata[4:0] != 5'd0));
        if (gen_dly != 8'd0) begin gen_dly <= gen_dly - 8'd1; if (gen_dly == 8'd1) p_gen <= 1'b1; end
        if (rs_all != 0) rs_all <= rs_all - 4'd1;
        if (rs_txpll != 0) rs_txpll <= rs_txpll - 4'd1;
        if (rs_rxpll != 0) rs_rxpll <= rs_rxpll - 4'd1;
        if (rs_txdp != 0) rs_txdp <= rs_txdp - 4'd1;
        if (rs_rxdp != 0) rs_rxdp <= rs_rxdp - 4'd1;
        txb_seen <= txb_seen | txbuf; rxb_seen <= rxb_seen | rxbuf;      // sticky since the last clear (CMD bit 0)
        if (rst) begin
            loopback <= NEAR_END ? 3'b010 : 3'b000; tx_disable <= 1'b1; tx_pol <= 1'b0; rx_pol <= 1'b0; rx_lpm <= 1'b1;
            ppm_step <= '0; ppm_en <= 1'b0; ppm_sel <= 1'b0; txb_seen <= '0; rxb_seen <= '0;
            rs_all <= '0; rs_txpll <= '0; rs_rxpll <= '0; rs_txdp <= '0; rs_rxdp <= '0; gen_dly <= '0;
            my_mac <= 48'h0A58_0000_0002; venue_mac <= 48'h0F58_0000_0002;
            my_ip <= 32'hC0A8_3A0A; venue_ip <= 32'hC0A8_3A0F; sport <= 16'd5800;
            port_feed <= 16'd5800; port_order <= 16'd5801; port_probe <= 16'd5802;
            thr <= 32'd9975; qty <= 32'd100; arm <= 1'b0; kill <= 1'b0; trade_en <= TRADE;
            gen_kind <= 2'd2; gen_len <= 16'd66; gen_inst <= 16'd1; gen_price <= 32'd9950; gen_interval <= 32'd2000; gen_count <= 32'd1;
            i2c_scl_r <= 1'b0; i2c_sda_r <= 1'b0; sm_en <= 1'b0; sm_valid <= 1'b0; sm_data <= '0; sm_addr_r <= '0;
            rx_snap <= '0; tx_snap <= '0;
            for (int i = 0; i < NCW; i++) begin c2[i] <= '0; c2s[i] <= '0; end
            c2[C_CTRL] <= 32'h10; c2[C_THR] <= 32'd1000000; c2[C_QTY] <= 32'd100; c2[C_MAXQTY] <= 32'd500; c2[C_MAXPOS] <= 32'd1000; c2[C_BAND] <= 32'd20000;
            c2s[C_THR] <= 32'd1000000; c2s[C_QTY] <= 32'd100; c2s[C_MAXQTY] <= 32'd500; c2s[C_MAXPOS] <= 32'd1000; c2s[C_BAND] <= 32'd20000;
            c2[C_ORDF0] <= 32'h4E505933; c2[C_ORDF1] <= 32'h4E4E;
            c2[C_WATCH] <= 32'h20202020; c2[C_WATCH+1] <= 32'h41414120; c2[C_WATCH+2] <= 32'h20202020; c2[C_WATCH+3] <= 32'h42424220;
            c2[C_WATCH+4] <= 32'h20202020; c2[C_WATCH+5] <= 32'h43434320; c2[C_WATCH+6] <= 32'h20202020; c2[C_WATCH+7] <= 32'h44444420;
            c2[C_FEEDIP] <= 32'hC0A83A0A; c2[C_FEEDPORT] <= 32'd5810; c2[C_TCPSEQ] <= 32'd1; c2[C_TCPACK] <= 32'd1;
            c2_cmd_seq <= '0; c2_rpw_seq <= '0; c2_tcpf_seq <= '0; c2_cmd_bits <= '0; stat2_snap <= '0;
            es_raw_addr <= '0; es_raw_wd <= '0; pt_horz <= '0; pt_code <= '0; pt_neg <= 1'b0; pt_ut <= 1'b0; pt_range <= '0; pt_pre_scale <= '0; pt_tmo_clks <= 32'd500_000_000;
            tx_diff_r <= 5'b11000; tx_pre_r <= '0; tx_post_r <= '0; dfelpm_r <= 1'b0;
        end else begin
            sm_en <= 1'b0;
            if (sm_rdy) begin sm_data <= sm_do; sm_valid <= 1'b1; end
            if (h_we) begin
                case (h_addr)
                    12'h00C: begin loopback <= h_wdata[2:0]; tx_disable <= h_wdata[3]; tx_pol <= h_wdata[4]; rx_pol <= h_wdata[5]; rx_lpm <= h_wdata[6]; end
                    12'h010: begin
                        if (h_wdata[0]) rs_all <= 4'd8;
                        if (h_wdata[1]) rs_txpll <= 4'd8;
                        if (h_wdata[2]) rs_rxpll <= 4'd8;
                        if (h_wdata[3]) rs_txdp <= 4'd8;
                        if (h_wdata[4]) rs_rxdp <= 4'd8;
                    end
                    12'h01C: begin ppm_step <= h_wdata[4:0]; ppm_en <= h_wdata[5]; ppm_sel <= h_wdata[6]; end
                    12'h018: begin
                        p_clr <= h_wdata[0]; if (h_wdata[0]) begin txb_seen <= txbuf; rxb_seen <= rxbuf; end if (h_wdata[1]) gen_dly <= 8'd200;
                        if (h_wdata[2]) begin rx_snap <= rx_live; tx_snap <= tx_live; stat2_snap <= stat2_live; end
                    end
                    12'h024: if (EYESCAN) es_raw_addr <= h_wdata[9:0];
                    12'h028: if (EYESCAN) es_raw_wd <= h_wdata[15:0];
                    12'h02C: if (EYESCAN) begin es_raw_rd_p <= h_wdata[0]; es_raw_wr_p <= h_wdata[1]; es_start_p <= h_wdata[2]; es_clr_p <= h_wdata[3]; end
                    12'h034: if (EYESCAN) begin pt_horz <= h_wdata[11:0]; pt_code <= h_wdata[18:12]; pt_neg <= h_wdata[19]; pt_ut <= h_wdata[20]; pt_range <= h_wdata[22:21]; pt_pre_scale <= h_wdata[27:23]; end
                    12'h038: if (EYESCAN) pt_tmo_clks <= h_wdata;
                    12'h084: if (EYESCAN) begin tx_diff_r <= h_wdata[4:0]; tx_pre_r <= h_wdata[9:5]; tx_post_r <= h_wdata[14:10]; dfelpm_r <= h_wdata[16]; end
                    12'h040: my_mac[31:0] <= h_wdata;
                    12'h044: my_mac[47:32] <= h_wdata[15:0];
                    12'h048: venue_mac[31:0] <= h_wdata;
                    12'h04C: venue_mac[47:32] <= h_wdata[15:0];
                    12'h050: my_ip <= h_wdata;
                    12'h054: venue_ip <= h_wdata;
                    12'h058: begin port_feed <= h_wdata[15:0]; sport <= h_wdata[31:16]; end
                    12'h05C: begin port_order <= h_wdata[15:0]; port_probe <= h_wdata[31:16]; end
                    12'h060: thr <= h_wdata;
                    12'h064: qty <= h_wdata;
                    12'h068: begin arm <= h_wdata[0]; kill <= h_wdata[1]; trade_en <= h_wdata[2]; gen_kind <= h_wdata[5:4]; end
                    12'h06C: begin gen_len <= h_wdata[15:0]; gen_inst <= h_wdata[31:16]; end
                    12'h070: gen_price <= h_wdata;
                    12'h074: gen_interval <= h_wdata;
                    12'h078: gen_count <= h_wdata;
                    12'h080: begin i2c_scl_r <= h_wdata[0]; i2c_sda_r <= h_wdata[1]; end
                    12'h090: begin sm_addr_r <= h_wdata[7:0]; sm_en <= 1'b1; sm_valid <= 1'b0; end
                    default: if (h_addr >= 12'h300 && h_addr < 12'h380) begin
                        case (c2_wi)
                            C_CTRL:     c2[C_CTRL] <= {h_wdata[31:16], 9'd0, h_wdata[6:0]};      // bits 6:0 flags (6 REF_SW), 31:16 HOLDOFF; immediate, not staged
                            C_ORDF1:    c2[C_ORDF1] <= {16'd0, h_wdata[15:0]};
                            C_FEEDPORT: c2[C_FEEDPORT] <= {16'd0, h_wdata[15:0]};
                            C_CMD:      begin
                                c2_cmd_bits <= h_wdata[15:0]; c2_cmd_seq <= c2_cmd_seq + 8'd1;
                                if (h_wdata[M_COMMIT]) for (int i = 0; i < NCW; i++) if (is_staged(i)) c2[i] <= c2s[i];     // every staged limit changes in this one clock
                            end
                            C_THR, C_QTY, C_MAXQTY, C_MAXPOS, C_BAND, C_PXOFF, C_REFPX, C_REFAGE: c2s[c2_wi] <= h_wdata;     // staged: no effect until IT_CMD COMMIT
                            C_RPW:      c2[C_RPW] <= {24'd0, h_wdata[7:0]};
                            C_RPCFG:    c2[C_RPCFG] <= {16'd0, h_wdata[15:0]};
                            C_RPWHI:    begin c2[C_RPWHI] <= h_wdata; c2_rpw_seq <= c2_rpw_seq + 8'd1; end
                            C_CAPADDR:  c2[C_CAPADDR] <= {25'd0, h_wdata[6:0]};
                            C_TCPFA:    c2[C_TCPFA] <= {19'd0, h_wdata[12:8], 3'd0, h_wdata[4:0]};
                            C_TCPFD:    begin c2[C_TCPFD] <= h_wdata; c2_tcpf_seq <= c2_tcpf_seq + 8'd1; end
                            default:    if (c2_wi < C_TCPFD) c2[c2_wi] <= h_wdata;     // words 0 to 27 not listed above
                        endcase
                    end
                endcase
            end
        end
    end
    always_comb begin
        rd = '0;
        case (h_addr)
            12'h000: rd = ID;
            12'h004: rd = BUILD_STAMP;
            12'h008: rd = {24'd0, 1'b1, 1'b0, (RATE_MATCH && RM_OWN), EYESCAN, RATE_MATCH, TRADE, NEAR_END, 1'b1};
            12'h00C: rd = {25'd0, rx_lpm, rx_pol, tx_pol, tx_disable, loopback};
            12'h01C: rd = {25'd0, ppm_sel, ppm_en, ppm_step};
            12'h020: rd = {22'd0, rxb_seen, txb_seen, rxbuf, txbuf};
            12'h014: rd = {19'd0, tx_fault_c, rx_los_c, mod_abs_c, pcs_lock, cdr_stable, 2'b00, rxpmadone, txpmadone, cdrlock, pgood, rx_done, tx_done};
            12'h024: rd = EYESCAN ? {22'd0, es_raw_addr} : 32'd0;
            12'h028: rd = EYESCAN ? {16'd0, es_raw_rd} : 32'd0;
            12'h030: rd = EYESCAN ? {es_pt_count, es_step[3:0], es_status, 3'd0, es_rej, es_drptmo, es_ptmo, es_done, es_busy} : 32'd0;
            12'h034: rd = EYESCAN ? {4'd0, pt_pre_scale, pt_range, pt_ut, pt_neg, pt_code, pt_horz} : 32'd0;
            12'h038: rd = EYESCAN ? pt_tmo_clks : 32'd0;
            12'h03C: rd = EYESCAN ? {es_res_samp, es_res_err} : 32'd0;
            12'h084: rd = EYESCAN ? {15'd0, dfelpm_r, 1'b0, tx_post_r, tx_pre_r, tx_diff_r} : 32'd0;
            12'h040: rd = my_mac[31:0];
            12'h044: rd = {16'd0, my_mac[47:32]};
            12'h048: rd = venue_mac[31:0];
            12'h04C: rd = {16'd0, venue_mac[47:32]};
            12'h050: rd = my_ip;
            12'h054: rd = venue_ip;
            12'h058: rd = {sport, port_feed};
            12'h05C: rd = {port_probe, port_order};
            12'h060: rd = thr;
            12'h064: rd = qty;
            12'h068: rd = {26'd0, gen_kind, 1'b0, trade_en, kill, arm};
            12'h06C: rd = {gen_inst, gen_len};
            12'h070: rd = gen_price;
            12'h074: rd = gen_interval;
            12'h078: rd = gen_count;
            12'h080: rd = {22'd0, sda_c, scl_c, 6'd0, i2c_sda_r, i2c_scl_r};
            12'h090: rd = {24'd0, sm_addr_r};
            12'h094: rd = {15'd0, sm_valid, sm_data};
            default: begin
                if (h_addr >= 12'h300 && h_addr < 12'h380) begin
                    rd = (c2_wi < NCW) ? c2[c2_wi] : 32'd0;
                    if (c2_wi < NCW && is_staged(c2_wi)) rd = c2s[c2_wi];                  // a read returns the staged value; the active one differs until COMMIT (IT_CMD bit 0 reads 1 meanwhile)
                    if (c2_wi == C_CMD) rd = {8'd0, c2_cmd_seq, 15'd0, lim_pending};
                    if (c2_wi == C_RPW) rd = {8'd0, c2_rpw_seq, 8'd0, c2[C_RPW][7:0]};
                    if (c2_wi == C_TCPFA) rd = {8'd0, c2_tcpf_seq, c2[C_TCPFA][15:0]};
                    if (c2_wi == C_TCPFD) rd = c2[C_TCPFD];
                    if (c2_wi > C_RPCFG && c2_wi < C_REFPX) rd = 32'd0;
                end
                else if (h_addr >= 12'h400 && h_addr < 12'h400 + 12'(4 * NSW)) rd = stat2_snap[32 * s2_i +: 32];
                else if (h_addr >= 12'h100 && h_addr < 12'h100 + 12'(4 * NRXW)) rd = rx_snap[32 * rx_i +: 32];
                else if (h_addr >= 12'h200 && h_addr < 12'h200 + 12'(4 * NTXW)) rd = tx_snap[32 * tx_i +: 32];
            end
        endcase
    end
    always_ff @(posedge clk) h_rdata <= rd;

    // the GT's data ports belong to our paths: the transmit words come from tx_path; the receive words go to rx_path (above)
    assign sfp_tx_disable = tx_disable;
    assign i2c_scl_low = i2c_scl_r;
    assign i2c_sda_low = i2c_sda_r;
    assign sm_addr = sm_addr_r;
    assign led = {pcs_lock, tx_done && rx_done};
    logic _unused;
    assign _unused = &{1'b0, h_re, sm_rdy, p_snap, utx_act_t, urx_act_r};
endmodule
