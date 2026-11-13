// gth_serdes_core.sv: one GTH channel at 10.3125 Gb/s with PRBS generation and checking and a host register block (brief 56A).
//
// The GT Wizard core `gth_wiz` (ip/amd_ip.tcl; RAW data, QPLL0, 156.25 MHz reference, 64-bit user data on a 32-bit internal
// data path, user clocks and reset helper inside the core) carries the serial link. Around it:
//   - prbs_gen64 / prbs_chk64: fabric PRBS-7/15/23/31 on the 64-bit user data (bit errors counted exactly);
//   - the GTH's own PRBS generator and checker (TXPRBSSEL / RXPRBSSEL), counted as cycles with an error;
//   - control and status registers on a 32-bit host bus (docs/register_map.md is the specification), counters read from a
//     coherent snapshot, the SFP+ control pins and an I2C bit-bang port, a DRP window onto the channel (for brief 56C's eye
//     scan and PLL work) and a window onto the SYSMON (die temperature and rails: house rule, operating conditions).
// Clock domains: clk (free-running, 100 MHz: registers, reset helper, DRP), tx_clk (TXUSRCLK2) and rx_clk (RXUSRCLK2), both from
// the GT. Every crossing is an XPM macro: flags and levels with xpm_cdc_single/array_single, pulses with xpm_cdc_pulse, the
// counter snapshot with xpm_cdc_handshake.
module gth_serdes_core #(
    parameter logic [31:0] BUILD_STAMP = 32'h0
) (
    input  logic        clk,
    input  logic        rst,
    // host register bus (jtag_bus); a read's data must be valid two clocks after h_re (every read is side-effect free)
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    // the link
    input  logic        refclk,
    input  logic        rx_p,
    input  logic        rx_n,
    output logic        tx_p,
    output logic        tx_n,
    // SFP+ cage
    output logic        sfp_tx_disable,
    input  logic        sfp_mod_abs,
    input  logic        sfp_rx_los,
    input  logic        sfp_tx_fault,
    output logic        i2c_scl_low,
    output logic        i2c_sda_low,
    input  logic        i2c_scl_i,
    input  logic        i2c_sda_i,
    // SYSMON DRP (clk domain)
    output logic        sm_en,
    output logic [7:0]  sm_addr,
    input  logic [15:0] sm_do,
    input  logic        sm_rdy,
    output logic [1:0]  led
);
    import prbs64_pkg::*;

    // ---------------------------------------------------------------- registers (clk domain)
    logic [2:0]  loopback;
    logic        tx_disable;
    logic [3:0]  txprbssel, rxprbssel;
    logic [1:0]  fab_poly;
    logic        tx_pol, rx_pol, rx_lpm, tx_idle, fab_tx_en, cdr_hold;
    logic [4:0]  txdiffctrl, txpost, txpre, ppm_step;
    logic        ppm_en, ppm_sel, eye_reset, eye_trig;
    logic        i2c_scl_r, i2c_sda_r;
    logic [7:0]  sm_addr_r;
    logic        sm_valid;
    logic [15:0] sm_data;
    logic [9:0]  drp_addr_r;
    logic [15:0] drp_di_r, drp_do_r;
    logic        drp_busy, drp_done, drp_en_p, drp_we_r;
    logic [3:0]  rs_all, rs_txpll, rs_rxpll, rs_txdp, rs_rxdp;
    logic        p_clr, p_ferr_fab, p_ferr_hard, p_snap;
    logic [5:0]  sticky;
    logic [15:0] snap_count;

    // control values as seen in the GT's clock domains, and pulses delivered there
    logic [3:0] txprbssel_t, rxprbssel_r;
    logic [4:0] ppm_step_t;
    logic       tx_pol_t, tx_idle_t, ppm_en_t, ppm_sel_t, rx_pol_r, fab_tx_en_t;
    logic [1:0] poly_t, poly_r;
    logic       ferr_fab_t, ferr_hard_t, clr_r, rx_prbs_cntrst, fab_lock_rx;

    localparam logic [31:0] ID = 32'h56A0_0001;

    // ---------------------------------------------------------------- the GT Wizard core
    logic        txusr2, rxusr2;
    logic        tx_done_t, rx_done_r, cdr_stable_c, pgood_c, cdrlock_c, txpmadone_c, rxpmadone_c, utx_act_t, urx_act_r;
    logic        hard_err_r, hard_lock_r, eyedat_r;
    logic [63:0] tx_data, rx_data;
    logic [15:0] gt_drpdo;
    logic        gt_drprdy;
    logic        txpmadone, rxpmadone, tx_done, rx_done, cdr_stable, pgood, cdrlock;
    logic        utx_rst, urx_rst;
    logic        tx_q, rx_q, fl_q, hl_q;
    logic [5:0]  sticky_set;
    // a fall event in the clock of a STICKY write is kept (set wins over the clear of that bit)
    always_comb sticky_set = {2'b00, hl_q && !hard_locked_c, fl_q && !fab_locked_c, rx_q && !rx_done, tx_q && !tx_done};
    // user-clock helpers are held in reset until the PMA of each direction is out of reset (wizard example design)
    assign utx_rst = ~txpmadone;
    assign urx_rst = ~rxpmadone;
    gth_wiz u_gt (
        .gtwiz_userclk_tx_reset_in(utx_rst), .gtwiz_userclk_tx_srcclk_out(), .gtwiz_userclk_tx_usrclk_out(),
        .gtwiz_userclk_tx_usrclk2_out(txusr2), .gtwiz_userclk_tx_active_out(utx_act_t),
        .gtwiz_userclk_rx_reset_in(urx_rst), .gtwiz_userclk_rx_srcclk_out(), .gtwiz_userclk_rx_usrclk_out(),
        .gtwiz_userclk_rx_usrclk2_out(rxusr2), .gtwiz_userclk_rx_active_out(urx_act_r),
        .gtwiz_reset_clk_freerun_in(clk), .gtwiz_reset_all_in(rst || (rs_all != 4'd0)),
        .gtwiz_reset_tx_pll_and_datapath_in(rs_txpll != 4'd0), .gtwiz_reset_tx_datapath_in(rs_txdp != 4'd0),
        .gtwiz_reset_rx_pll_and_datapath_in(rs_rxpll != 4'd0), .gtwiz_reset_rx_datapath_in(rs_rxdp != 4'd0),
        .gtwiz_reset_rx_cdr_stable_out(cdr_stable_c), .gtwiz_reset_tx_done_out(tx_done_t),
        .gtwiz_reset_rx_done_out(rx_done_r),
        .gtwiz_userdata_tx_in(tx_data), .gtwiz_userdata_rx_out(rx_data),
        .gtrefclk00_in(refclk), .qpll0outclk_out(), .qpll0outrefclk_out(),
        .drpaddr_in(drp_addr_r), .drpclk_in(clk), .drpdi_in(drp_di_r), .drpen_in(drp_en_p), .drpwe_in(drp_we_r),
        .drpdo_out(gt_drpdo), .drprdy_out(gt_drprdy),
        .eyescanreset_in(eye_reset), .eyescantrigger_in(eye_trig), .eyescandataerror_out(eyedat_r),
        .gthrxn_in(rx_n), .gthrxp_in(rx_p), .gthtxn_out(tx_n), .gthtxp_out(tx_p),
        .loopback_in(loopback), .rxcdrhold_in(cdr_hold), .rxdfelpmreset_in(1'b0), .rxlpmen_in(rx_lpm),
        .rxpolarity_in(rx_pol_r), .rxprbscntreset_in(rx_prbs_cntrst), .rxprbssel_in(rxprbssel_r),
        .txdiffctrl_in(txdiffctrl), .txelecidle_in(tx_idle_t), .txpippmen_in(ppm_en_t), .txpippmsel_in(ppm_sel_t),
        .txpippmstepsize_in(ppm_step_t), .txpolarity_in(tx_pol_t), .txpostcursor_in(txpost), .txprbsforceerr_in(ferr_hard_t),
        .txprbssel_in(txprbssel_t), .txprecursor_in(txpre),
        .gtpowergood_out(pgood_c), .rxcdrlock_out(cdrlock_c), .rxpmaresetdone_out(rxpmadone_c),
        .rxprbserr_out(hard_err_r), .rxprbslocked_out(hard_lock_r), .txpmaresetdone_out(txpmadone_c));

    // levels from the GT into clk
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_tx (.src_clk(txusr2), .src_in(tx_done_t), .dest_clk(clk), .dest_out(tx_done));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_rx (.src_clk(rxusr2), .src_in(rx_done_r), .dest_clk(clk), .dest_out(rx_done));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_cs (.src_clk(1'b0), .src_in(cdr_stable_c), .dest_clk(clk), .dest_out(cdr_stable));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_pg (.src_clk(1'b0), .src_in(pgood_c), .dest_clk(clk), .dest_out(pgood));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_cl (.src_clk(1'b0), .src_in(cdrlock_c), .dest_clk(clk), .dest_out(cdrlock));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_tp (.src_clk(1'b0), .src_in(txpmadone_c), .dest_clk(clk), .dest_out(txpmadone));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_rp (.src_clk(1'b0), .src_in(rxpmadone_c), .dest_clk(clk), .dest_out(rxpmadone));
    logic fab_locked_c, hard_locked_c, eyedat_c, mod_abs_c, rx_los_c, tx_fault_c, scl_c, sda_c;
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(1)) u_s_fl (.src_clk(rxusr2), .src_in(fab_lock_rx), .dest_clk(clk), .dest_out(fab_locked_c));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(1)) u_s_hl (.src_clk(rxusr2), .src_in(hard_lock_r), .dest_clk(clk), .dest_out(hard_locked_c));
    xpm_cdc_single #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(1)) u_s_ed (.src_clk(rxusr2), .src_in(eyedat_r), .dest_clk(clk), .dest_out(eyedat_c));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_ma (.src_clk(1'b0), .src_in(sfp_mod_abs), .dest_clk(clk), .dest_out(mod_abs_c));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_lo (.src_clk(1'b0), .src_in(sfp_rx_los), .dest_clk(clk), .dest_out(rx_los_c));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_tf (.src_clk(1'b0), .src_in(sfp_tx_fault), .dest_clk(clk), .dest_out(tx_fault_c));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_sc (.src_clk(1'b0), .src_in(i2c_scl_i), .dest_clk(clk), .dest_out(scl_c));
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_s_sd (.src_clk(1'b0), .src_in(i2c_sda_i), .dest_clk(clk), .dest_out(sda_c));

    // controls from clk into the GT's clocked ports
    xpm_cdc_array_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(1), .WIDTH(14)) u_c_tx (
        .src_clk(clk), .src_in({txprbssel, tx_pol, tx_idle, ppm_en, ppm_sel, ppm_step, fab_tx_en}), .dest_clk(txusr2),
        .dest_out({txprbssel_t, tx_pol_t, tx_idle_t, ppm_en_t, ppm_sel_t, ppm_step_t, fab_tx_en_t}));
    xpm_cdc_array_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(1), .WIDTH(2)) u_c_ptx (
        .src_clk(clk), .src_in(fab_poly), .dest_clk(txusr2), .dest_out(poly_t));
    xpm_cdc_array_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(1), .WIDTH(7)) u_c_rx (
        .src_clk(clk), .src_in({rxprbssel, rx_pol, fab_poly}), .dest_clk(rxusr2), .dest_out({rxprbssel_r, rx_pol_r, poly_r}));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_p_fe (
        .src_clk(clk), .src_pulse(p_ferr_fab), .src_rst(1'b0), .dest_clk(txusr2), .dest_pulse(ferr_fab_t), .dest_rst(1'b0));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_p_fh (
        .src_clk(clk), .src_pulse(p_ferr_hard), .src_rst(1'b0), .dest_clk(txusr2), .dest_pulse(ferr_hard_t), .dest_rst(1'b0));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_p_cl (
        .src_clk(clk), .src_pulse(p_clr), .src_rst(1'b0), .dest_clk(rxusr2), .dest_pulse(clr_r), .dest_rst(1'b0));
    // the hard checker needs a reset (or a counter reset) after RXPRBSSEL changes (UG576): pulse one when the selection changes
    logic [3:0] rxprbssel_q;
    always_ff @(posedge rxusr2) rxprbssel_q <= rxprbssel_r;
    assign rx_prbs_cntrst = clr_r || (rxprbssel_q != rxprbssel_r);

    // ---------------------------------------------------------------- fabric PRBS
    logic tx_en_g;
    logic [63:0] gen_d;
    assign tx_en_g = tx_done_t && fab_tx_en_t;
    prbs_gen64 u_gen (.clk(txusr2), .rst(!tx_done_t), .sel(poly_t), .en(tx_en_g), .force_err(ferr_fab_t), .data(gen_d));
    assign tx_data = gen_d;
    logic        chk_lock, chk_lost;
    logic [63:0] c_words, c_errb, h_cyc, h_err;
    logic [31:0] c_errw;
    logic [15:0] c_loss;
    assign fab_lock_rx = chk_lock;
    prbs_chk64 u_chk (.clk(rxusr2), .rst(!rx_done_r), .sel(poly_r), .en(rx_done_r), .data(rx_data), .clr(clr_r),
                      .locked(chk_lock), .lost_pulse(chk_lost), .words(c_words), .err_bits(c_errb), .err_words(c_errw),
                      .lock_losses(c_loss));
    always_ff @(posedge rxusr2) begin
        if (!rx_done_r || clr_r) begin h_cyc <= '0; h_err <= '0; end
        else begin
            if (hard_lock_r) h_cyc <= h_cyc + 64'd1;
            if (hard_lock_r && hard_err_r) h_err <= h_err + 64'd1;
        end
    end
    // counter snapshot to clk: a running handshake of a registered copy
    localparam int CW = 304;
    logic [CW-1:0] src_vec, dst_vec, live, snap;
    logic          hs_send, hs_rcv, hs_req, hs_ack;
    always_ff @(posedge rxusr2) begin
        if (!hs_send && !hs_rcv) begin src_vec <= {c_words, c_errb, c_errw, c_loss, h_cyc, h_err}; hs_send <= 1'b1; end
        else if (hs_rcv) hs_send <= 1'b0;
    end
    xpm_cdc_handshake #(.DEST_EXT_HSK(1), .DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_SYNC_FF(4), .WIDTH(CW)) u_snap (
        .src_clk(rxusr2), .src_in(src_vec), .src_send(hs_send), .src_rcv(hs_rcv),
        .dest_clk(clk), .dest_out(dst_vec), .dest_req(hs_req), .dest_ack(hs_ack));
    always_ff @(posedge clk) hs_ack <= hs_req;       // external handshake: acknowledge each request one clock after it is taken (live <= dst_vec below)
    initial hs_send = 1'b0;

    // ---------------------------------------------------------------- host registers
    logic [31:0] rd;
    always_ff @(posedge clk) begin
        p_clr <= 1'b0; p_ferr_fab <= 1'b0; p_ferr_hard <= 1'b0; p_snap <= 1'b0; drp_en_p <= 1'b0;
        if (rs_all != 0) rs_all <= rs_all - 4'd1;
        if (rs_txpll != 0) rs_txpll <= rs_txpll - 4'd1;
        if (rs_rxpll != 0) rs_rxpll <= rs_rxpll - 4'd1;
        if (rs_txdp != 0) rs_txdp <= rs_txdp - 4'd1;
        if (rs_rxdp != 0) rs_rxdp <= rs_rxdp - 4'd1;
        if (hs_req) live <= dst_vec;
        if (rst) begin
            loopback <= 3'd0; tx_disable <= 1'b1; txprbssel <= '0; rxprbssel <= '0; fab_poly <= 2'd3; tx_pol <= 1'b0;
            rx_pol <= 1'b0; rx_lpm <= 1'b1; tx_idle <= 1'b0; cdr_hold <= 1'b0; fab_tx_en <= 1'b1;
            txdiffctrl <= 5'b11000; txpost <= '0; txpre <= '0; ppm_step <= '0; ppm_en <= 1'b0; ppm_sel <= 1'b0;
            eye_reset <= 1'b0; eye_trig <= 1'b0; i2c_scl_r <= 1'b0; i2c_sda_r <= 1'b0; sticky <= '0; snap <= '0;
            snap_count <= '0; rs_all <= '0; rs_txpll <= '0; rs_rxpll <= '0; rs_txdp <= '0; rs_rxdp <= '0;
            sm_en <= 1'b0; sm_valid <= 1'b0; sm_data <= '0; sm_addr_r <= '0; drp_addr_r <= '0; drp_di_r <= '0;
            drp_do_r <= '0; drp_busy <= 1'b0; drp_done <= 1'b0; drp_we_r <= 1'b0; live <= '0;
        end else begin
            sm_en <= 1'b0;
            // sticky bits: the falling edge of a level that was up
            tx_q <= tx_done; rx_q <= rx_done; fl_q <= fab_locked_c; hl_q <= hard_locked_c;
            if (tx_q && !tx_done)         sticky[0] <= 1'b1;
            if (rx_q && !rx_done)         sticky[1] <= 1'b1;
            if (fl_q && !fab_locked_c)    sticky[2] <= 1'b1;
            if (hl_q && !hard_locked_c)   sticky[3] <= 1'b1;
            if (sm_rdy) begin sm_data <= sm_do; sm_valid <= 1'b1; end
            if (drp_busy && gt_drprdy) begin if (!drp_we_r) drp_do_r <= gt_drpdo; drp_busy <= 1'b0; drp_done <= 1'b1; end
            if (h_we) begin
                case (h_addr)
                    12'h00C: begin loopback <= h_wdata[2:0]; tx_disable <= h_wdata[3]; txprbssel <= h_wdata[7:4];
                        rxprbssel <= h_wdata[11:8]; fab_poly <= h_wdata[13:12]; tx_pol <= h_wdata[14]; rx_pol <= h_wdata[15];
                        rx_lpm <= h_wdata[16]; tx_idle <= h_wdata[17]; fab_tx_en <= h_wdata[18]; cdr_hold <= h_wdata[19]; end
                    12'h010: begin
                        if (h_wdata[0]) rs_all <= 4'd8;
                        if (h_wdata[1]) rs_txpll <= 4'd8;
                        if (h_wdata[2]) rs_rxpll <= 4'd8;
                        if (h_wdata[3]) rs_txdp <= 4'd8;
                        if (h_wdata[4]) rs_rxdp <= 4'd8;
                        p_clr <= h_wdata[5]; p_ferr_fab <= h_wdata[6]; p_ferr_hard <= h_wdata[7];
                        if (h_wdata[8]) begin snap <= live; snap_count <= snap_count + 16'd1; end
                    end
                    12'h018: sticky <= (sticky & ~h_wdata[5:0]) | sticky_set;
                    12'h01C: begin txdiffctrl <= h_wdata[4:0]; txpost <= h_wdata[9:5]; txpre <= h_wdata[14:10];
                        ppm_step <= h_wdata[19:15]; ppm_en <= h_wdata[20]; ppm_sel <= h_wdata[21]; end
                    12'h050: begin i2c_scl_r <= h_wdata[0]; i2c_sda_r <= h_wdata[1]; end
                    12'h060: begin sm_addr_r <= h_wdata[7:0]; sm_en <= 1'b1; sm_valid <= 1'b0; end
                    12'h070: drp_addr_r <= h_wdata[9:0];
                    12'h074: drp_di_r <= h_wdata[15:0];
                    12'h078: if (h_wdata[0] && !drp_busy) begin drp_en_p <= 1'b1; drp_we_r <= h_wdata[1]; drp_busy <= 1'b1; drp_done <= 1'b0; end
                    12'h080: begin eye_reset <= h_wdata[0]; eye_trig <= h_wdata[1]; end
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
            12'h00C: rd = {12'd0, cdr_hold, fab_tx_en, tx_idle, rx_lpm, rx_pol, tx_pol, fab_poly, rxprbssel, txprbssel, tx_disable, loopback};
            12'h014: rd = {18'd0, tx_fault_c, rx_los_c, mod_abs_c, hard_locked_c, fab_locked_c, cdr_stable, 2'b00,
                           rxpmadone, txpmadone, cdrlock, pgood, rx_done, tx_done};
            12'h018: rd = {26'd0, sticky};
            12'h01C: rd = {10'd0, ppm_sel, ppm_en, ppm_step, txpre, txpost, txdiffctrl};
            // counters come from the snapshot: {fab_words, fab_errbits, fab_errwords, lock_losses, hard_cycles, hard_err}
            12'h020: rd = snap[240 +: 32];
            12'h024: rd = snap[272 +: 32];
            12'h028: rd = snap[176 +: 32];
            12'h02C: rd = snap[208 +: 32];
            12'h030: rd = snap[144 +: 32];
            12'h034: rd = {16'd0, snap[128 +: 16]};
            12'h038: rd = snap[64 +: 32];
            12'h03C: rd = snap[96 +: 32];
            12'h040: rd = snap[0 +: 32];
            12'h044: rd = snap[32 +: 32];
            12'h048: rd = {16'd0, snap_count};
            12'h050: rd = {22'd0, sda_c, scl_c, 6'd0, i2c_sda_r, i2c_scl_r};
            12'h060: rd = {24'd0, sm_addr_r};
            12'h064: rd = {15'd0, sm_valid, sm_data};
            12'h070: rd = {22'd0, drp_addr_r};
            12'h074: rd = {16'd0, drp_do_r};
            12'h078: rd = {30'd0, drp_done, drp_busy};
            12'h080: rd = {23'd0, eyedat_c, 6'd0, eye_trig, eye_reset};
            default: rd = '0;
        endcase
    end
    always_ff @(posedge clk) h_rdata <= rd;

    assign sfp_tx_disable = tx_disable;
    assign i2c_scl_low = i2c_scl_r;
    assign i2c_sda_low = i2c_sda_r;
    assign sm_addr = sm_addr_r;
    assign led = {fab_locked_c, tx_done && rx_done};
    logic _unused;
    assign _unused = &{1'b0, h_re, sm_rdy, hs_req, pgood};
endmodule
