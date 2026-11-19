// b96_core.sv: everything of brief 96's KR260 10GBASE-R design except the board pins' buffers, the clock generator, the SYSMON and the JTAG
// front end (kr260_10g_top): the GT Wizard core carrying the line (the one of brief 56A: RAW, 64-bit user data, QPLL0, 156.25 MHz
// reference), our own PCS and MAC in each user-clock domain (tx_path, rx_path), the host register block (docs/register_map.md is the
// specification) and the crossings between the three clock domains:
//   clk (free-running 100 MHz: registers, reset helper) | tx_clk (TXUSRCLK2, 161.1328125 MHz) | rx_clk (RXUSRCLK2, recovered)
// Crossings: configuration, counters and status by hs_vec (XPM request/acknowledge handshake, always coherent); command pulses and
// the receive-to-transmit events by xpm_cdc_pulse; the order's fields (instrument, price, quantity, number) and the FCS verdict of the frame that
// caused it by xpm_cdc_array_single as a quasi-static bus (frame_src samples it 5 clocks after the order starts; `stale` counts misses).
module b96_core #(
    parameter logic [31:0] BUILD_STAMP = 32'h0,
    parameter bit          NEAR_END    = 1'b0,    // reset value of the loopback field: 1 = near-end PMA loopback (variant a)
    parameter bit          TRADE       = 1'b1     // 1 = the mock trading path is armed to be enabled (variant b); reported in FEATURES
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
    localparam int NRXW = 18;
    localparam int NTXW = 26;
    localparam logic [31:0] ID = 32'h96A0_0001;

    // ---------------------------------------------------------------- registers (clk domain)
    logic [2:0]  loopback;
    logic        tx_disable, tx_pol, rx_pol, rx_lpm;
    logic [3:0]  rs_all, rs_txpll, rs_rxpll, rs_txdp, rs_rxdp;
    logic        p_clr, p_gen, p_snap, p_seq, tx_done_q, rx_done_q;
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
    gth_wiz u_gt (
        .gtwiz_userclk_tx_reset_in(wz_utx), .gtwiz_userclk_tx_srcclk_out(), .gtwiz_userclk_tx_usrclk_out(),
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
        .drpaddr_in(10'd0), .drpclk_in(clk), .drpdi_in(16'd0), .drpen_in(1'b0), .drpwe_in(1'b0),
        .drpdo_out(), .drprdy_out(),
        .eyescanreset_in(1'b0), .eyescantrigger_in(1'b0), .eyescandataerror_out(),
        .gthrxn_in(rx_n), .gthrxp_in(rx_p), .gthtxn_out(tx_n), .gthtxp_out(tx_p),
        .loopback_in(loopback), .rxcdrhold_in(1'b0), .rxdfelpmreset_in(1'b0), .rxlpmen_in(rx_lpm),
        .rxpolarity_in(rx_pol_r), .rxprbscntreset_in(1'b0), .rxprbssel_in(4'd0),
        .txdiffctrl_in(5'b11000), .txelecidle_in(1'b0), .txpippmen_in(1'b0), .txpippmsel_in(1'b0),
        .txpippmstepsize_in(5'd0), .txpolarity_in(tx_pol_t), .txpostcursor_in(5'd0), .txprbsforceerr_in(1'b0),
        .txprbssel_in(4'd0), .txprecursor_in(5'd0),
        .gtpowergood_out(pgood_c), .rxcdrlock_out(cdrlock_c), .rxpmaresetdone_out(rxpmadone_c),
        .rxprbserr_out(), .rxprbslocked_out(), .txpmaresetdone_out(txpmadone_c));
    logic tx_pol_t, rx_pol_r;
    xpm_cdc_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(1)) u_c_tp (.src_clk(clk), .src_in(tx_pol), .dest_clk(txusr2), .dest_out(tx_pol_t));
    xpm_cdc_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(1)) u_c_rp (.src_clk(clk), .src_in(rx_pol), .dest_clk(rxusr2), .dest_out(rx_pol_r));

    // levels from the GT into clk (as 56A)
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_tx (.src_clk(txusr2), .src_in(tx_done_t), .dest_clk(clk), .dest_out(tx_done));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_rx (.src_clk(rxusr2), .src_in(rx_done_r), .dest_clk(clk), .dest_out(rx_done));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_cs (.src_clk(1'b0), .src_in(cdr_stable_c), .dest_clk(clk), .dest_out(cdr_stable));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_pg (.src_clk(1'b0), .src_in(pgood_c), .dest_clk(clk), .dest_out(pgood));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_cl (.src_clk(1'b0), .src_in(cdrlock_c), .dest_clk(clk), .dest_out(cdrlock));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_tp (.src_clk(1'b0), .src_in(txpmadone_c), .dest_clk(clk), .dest_out(txpmadone));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_rp (.src_clk(1'b0), .src_in(rxpmadone_c), .dest_clk(clk), .dest_out(rxpmadone));
    logic pcs_lock_rx, pcs_lock, mod_abs_c, rx_los_c, tx_fault_c, scl_c, sda_c;
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(1)) u_s_pl (.src_clk(rxusr2), .src_in(pcs_lock_rx), .dest_clk(clk), .dest_out(pcs_lock));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_ma (.src_clk(1'b0), .src_in(sfp_mod_abs), .dest_clk(clk), .dest_out(mod_abs_c));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_lo (.src_clk(1'b0), .src_in(sfp_rx_los), .dest_clk(clk), .dest_out(rx_los_c));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_tf (.src_clk(1'b0), .src_in(sfp_tx_fault), .dest_clk(clk), .dest_out(tx_fault_c));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_sc (.src_clk(1'b0), .src_in(i2c_scl_i), .dest_clk(clk), .dest_out(scl_c));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_sd (.src_clk(1'b0), .src_in(i2c_sda_i), .dest_clk(clk), .dest_out(sda_c));

    // ---------------------------------------------------------------- the two paths and their crossings
    logic [CFGW-1:0] cfg_tx, cfg_rx;
    hs_vec #(.W(CFGW)) u_cfg_tx (.src_clk(clk), .src_vec(cfg), .dst_clk(txusr2), .dst_vec(cfg_tx));
    hs_vec #(.W(CFGW)) u_cfg_rx (.src_clk(clk), .src_vec(cfg), .dst_clk(rxusr2), .dst_vec(cfg_rx));
    logic clr_tx, clr_rx, gen_tx, seq_tx, seq_rx;
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_p_ct (.src_clk(clk), .src_pulse(p_clr), .src_rst(1'b0), .dest_clk(txusr2), .dest_pulse(clr_tx), .dest_rst(1'b0));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_p_cr (.src_clk(clk), .src_pulse(p_clr), .src_rst(1'b0), .dest_clk(rxusr2), .dest_pulse(clr_rx), .dest_rst(1'b0));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_p_st (.src_clk(clk), .src_pulse(p_seq), .src_rst(1'b0), .dest_clk(txusr2), .dest_pulse(seq_tx), .dest_rst(1'b0));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_p_sr (.src_clk(clk), .src_pulse(p_seq), .src_rst(1'b0), .dest_clk(rxusr2), .dest_pulse(seq_rx), .dest_rst(1'b0));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_p_gt (.src_clk(clk), .src_pulse(p_gen), .src_rst(1'b0), .dest_clk(txusr2), .dest_pulse(gen_tx), .dest_rst(1'b0));

    logic        r_fire, r_sop, r_feed, r_order, r_probe, r_verdict_v, r_verdict_bad;
    logic [15:0] r_inst;
    logic [31:0] r_price, r_qty, r_seq;
    logic [32 * NRXW - 1:0] rx_vec_r, rx_live;
    logic [32 * NTXW - 1:0] tx_vec_t, tx_live;
    logic        go_t, sop_t, feed_t, order_t, probe_t;
    logic [15:0] go_inst;
    logic [31:0] go_price, go_qty, go_seq;
    logic        vd_v, vd_bad;
    logic [31:0] r_verdict_seq, vd_seq;
    rx_path #(.NRXW(NRXW)) u_rx (.clk(rxusr2), .rst(!rx_done_r), .cfg(cfg_rx), .clr_p(clr_rx), .seq_p(seq_rx), .gt_d(rx_data), .fire(r_fire), .o_inst(r_inst),
        .o_price(r_price), .o_qty(r_qty), .o_seq(r_seq), .verdict_v(r_verdict_v), .verdict_bad(r_verdict_bad), .verdict_seq(r_verdict_seq), .rx_sop(r_sop),
        .cls_feed(r_feed), .cls_order(r_order), .cls_probe(r_probe), .lock(pcs_lock_rx), .rx_vec(rx_vec_r));
    xpm_cdc_pulse #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_p_go (.src_clk(rxusr2), .src_pulse(r_fire), .src_rst(1'b0), .dest_clk(txusr2), .dest_pulse(go_t), .dest_rst(1'b0));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_p_so (.src_clk(rxusr2), .src_pulse(r_sop), .src_rst(1'b0), .dest_clk(txusr2), .dest_pulse(sop_t), .dest_rst(1'b0));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_p_fe (.src_clk(rxusr2), .src_pulse(r_feed), .src_rst(1'b0), .dest_clk(txusr2), .dest_pulse(feed_t), .dest_rst(1'b0));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_p_or (.src_clk(rxusr2), .src_pulse(r_order), .src_rst(1'b0), .dest_clk(txusr2), .dest_pulse(order_t), .dest_rst(1'b0));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_p_pr (.src_clk(rxusr2), .src_pulse(r_probe), .src_rst(1'b0), .dest_clk(txusr2), .dest_pulse(probe_t), .dest_rst(1'b0));
    xpm_cdc_array_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0), .WIDTH(146)) u_bus (
        .src_clk(rxusr2), .src_in({r_verdict_v, r_verdict_bad, r_verdict_seq, r_inst, r_price, r_qty, r_seq}), .dest_clk(txusr2),
        .dest_out({vd_v, vd_bad, vd_seq, go_inst, go_price, go_qty, go_seq}));
    tx_path #(.NTXW(NTXW)) u_tx (.clk(txusr2), .rst(!tx_done_t), .cfg(cfg_tx), .clr_p(clr_tx), .seq_p(seq_tx), .gen_go_p(gen_tx), .go_p(go_t), .go_inst, .go_price,
        .go_qty, .go_seq, .verdict_v(vd_v), .verdict_bad(vd_bad), .verdict_seq(vd_seq), .rx_sop_p(sop_t), .rx_feed_p(feed_t), .rx_order_p(order_t),
        .rx_probe_p(probe_t), .gt_d(tx_data), .tx_vec(tx_vec_t));
    hs_vec #(.W(32 * NRXW)) u_rxv (.src_clk(rxusr2), .src_vec(rx_vec_r), .dst_clk(clk), .dst_vec(rx_live));
    hs_vec #(.W(32 * NTXW)) u_txv (.src_clk(txusr2), .src_vec(tx_vec_t), .dst_clk(clk), .dst_vec(tx_live));
    logic [32 * NRXW - 1:0] rx_snap;
    logic [32 * NTXW - 1:0] tx_snap;

    // ---------------------------------------------------------------- host registers
    logic [31:0] rd;
    int          rx_i, tx_i;
    assign rx_i = (int'(h_addr) - 256) >> 2;
    assign tx_i = (int'(h_addr) - 512) >> 2;
    initial begin p_seq = 1'b0; tx_done_q = 1'b0; rx_done_q = 1'b0; end
    logic [7:0]  gen_dly;      // the run command is held back so the configuration (hs_vec, a few dozen clocks) has arrived first
    always_ff @(posedge clk) begin
        p_clr <= 1'b0; p_gen <= 1'b0; p_snap <= 1'b0;
        // 97C: any restart of either side (a GT reset command, or either side's done level changing) restarts the order number on both sides
        tx_done_q <= tx_done; rx_done_q <= rx_done;
        p_seq <= (tx_done != tx_done_q) || (rx_done != rx_done_q) || (h_we && h_addr == 12'h010 && (h_wdata[4:0] != 5'd0));
        if (gen_dly != 8'd0) begin gen_dly <= gen_dly - 8'd1; if (gen_dly == 8'd1) p_gen <= 1'b1; end
        if (rs_all != 0) rs_all <= rs_all - 4'd1;
        if (rs_txpll != 0) rs_txpll <= rs_txpll - 4'd1;
        if (rs_rxpll != 0) rs_rxpll <= rs_rxpll - 4'd1;
        if (rs_txdp != 0) rs_txdp <= rs_txdp - 4'd1;
        if (rs_rxdp != 0) rs_rxdp <= rs_rxdp - 4'd1;
        if (rst) begin
            loopback <= NEAR_END ? 3'b010 : 3'b000; tx_disable <= 1'b1; tx_pol <= 1'b0; rx_pol <= 1'b0; rx_lpm <= 1'b1;
            rs_all <= '0; rs_txpll <= '0; rs_rxpll <= '0; rs_txdp <= '0; rs_rxdp <= '0; gen_dly <= '0;
            my_mac <= 48'h0A58_0000_0002; venue_mac <= 48'h0F58_0000_0002;
            my_ip <= 32'hC0A8_3A0A; venue_ip <= 32'hC0A8_3A0F; sport <= 16'd5800;
            port_feed <= 16'd5800; port_order <= 16'd5801; port_probe <= 16'd5802;
            thr <= 32'd9975; qty <= 32'd100; arm <= 1'b0; kill <= 1'b0; trade_en <= TRADE;
            gen_kind <= 2'd2; gen_len <= 16'd66; gen_inst <= 16'd1; gen_price <= 32'd9950; gen_interval <= 32'd2000; gen_count <= 32'd1;
            i2c_scl_r <= 1'b0; i2c_sda_r <= 1'b0; sm_en <= 1'b0; sm_valid <= 1'b0; sm_data <= '0; sm_addr_r <= '0;
            rx_snap <= '0; tx_snap <= '0;
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
                    12'h018: begin
                        p_clr <= h_wdata[0]; if (h_wdata[1]) gen_dly <= 8'd200;
                        if (h_wdata[2]) begin rx_snap <= rx_live; tx_snap <= tx_live; end
                    end
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
                    default: ;
                endcase
            end
        end
    end
    always_comb begin
        rd = '0;
        case (h_addr)
            12'h000: rd = ID;
            12'h004: rd = BUILD_STAMP;
            12'h008: rd = {29'd0, TRADE, NEAR_END, 1'b1};
            12'h00C: rd = {25'd0, rx_lpm, rx_pol, tx_pol, tx_disable, loopback};
            12'h014: rd = {19'd0, tx_fault_c, rx_los_c, mod_abs_c, pcs_lock, cdr_stable, 2'b00, rxpmadone, txpmadone, cdrlock, pgood, rx_done, tx_done};
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
                if (h_addr >= 12'h100 && h_addr < 12'h100 + 12'(4 * NRXW)) rd = rx_snap[32 * rx_i +: 32];
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
