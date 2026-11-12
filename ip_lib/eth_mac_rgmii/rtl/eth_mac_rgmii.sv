// eth_mac_rgmii.sv: tri-mode (10/100/1000 Mb/s) Ethernet MAC for an RGMII PHY, our own (ip_lib).
//
// Receive: RGMII (rgmii_rx, in the RX_CLK domain) -> an asynchronous FIFO into clk (gmii_cdc) -> mac_rx.
//   The cut-through view is always there: every frame byte leaves on rx_* one clock after it reaches mac_rx, before
//   the FCS is known, and rx_end_* gives the verdict at the end (the trading path's speculative path).
//   CUT_THROUGH = 0 adds a store-and-forward buffer (eth_rx_sf): good frames only, FCS removed, on an AXI-Stream
//   master with back-pressure. With CUT_THROUGH = 1 that buffer is not built and m_axis is idle.
// Transmit: an AXI-Stream slave (tlast ends the frame; tuser on any beat, or poison, marks it bad) -> mac_tx ->
//   rgmii_tx. Once a frame has started its bytes must keep coming: a beat missing when the MAC needs it (an underrun)
//   ends the frame with a bad FCS (tx_underrun). The MAC pads to MIN_DATA and adds the FCS.
// speed: 2 = 1000, 1 = 100, 0 = 10 Mb/s, from the PHY's link status (management is outside this block); change it
// only while no frame is passing. clk is 125 MHz at every speed; clk90 is the same clock 90 degrees later.
// rx_clk must already be on a clock buffer (the board top's job); the PHY's RX delay mode is the board's choice.

module eth_mac_rgmii #(
    parameter int CUT_THROUGH = 1,      // 1: cut-through only; 0: also the store-and-forward AXI-Stream output
    parameter int MIN_FRAME   = 64,     // receive: shortest good frame, FCS included
    parameter int MAX_FRAME   = 1522,   // receive: longest good frame, FCS included
    parameter int MIN_DATA    = 60,     // transmit: pad to this many bytes before the FCS
    parameter int IFG_BYTES   = 12,     // transmit: inter-frame gap in byte times
    parameter int SF_DEPTH    = 4096    // store-and-forward buffer, bytes (CUT_THROUGH = 0)
) (
    input  logic        clk,
    input  logic        clk90,
    input  logic        rst,
    input  logic [1:0]  speed,
    // RGMII
    input  logic        rgmii_rx_clk,
    input  logic [3:0]  rgmii_rxd,
    input  logic        rgmii_rx_ctl,
    output logic        rgmii_txc,
    output logic [3:0]  rgmii_txd,
    output logic        rgmii_tx_ctl,
    // receive, cut-through view
    output logic        rx_sof_pulse,   // the SFD reached mac_rx (timestamp point)
    output logic        rx_valid,
    output logic        rx_sof,
    output logic [7:0]  rx_data,
    output logic [10:0] rx_idx,
    output logic        rx_end_valid,
    output logic        rx_end_good,
    output logic        rx_end_fcs_err,
    output logic        rx_end_runt,
    output logic        rx_end_giant,
    output logic        rx_end_er,
    output logic [10:0] rx_end_len,
    output logic        rx_fifo_ovf,
    // receive, store-and-forward (CUT_THROUGH = 0)
    output logic [7:0]  m_axis_tdata,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready,
    output logic        m_axis_tlast,
    output logic        rx_sf_dropped,
    output logic        rx_sf_overflow,
    // transmit
    input  logic [7:0]  s_axis_tdata,
    input  logic        s_axis_tvalid,
    output logic        s_axis_tready,
    input  logic        s_axis_tlast,
    input  logic        s_axis_tuser,
    input  logic        tx_poison,
    output logic        tx_first_pulse, // the first preamble byte is on the wire side of the MAC
    output logic        tx_sof_pulse,
    output logic        tx_last_pulse,
    output logic        tx_last_poisoned,
    output logic        tx_underrun
);
    initial begin
        if (CUT_THROUGH != 0 && CUT_THROUGH != 1) $error("eth_mac_rgmii: CUT_THROUGH must be 0 or 1 (got %0d)", CUT_THROUGH);
        if (MIN_FRAME < 18 || MIN_FRAME > MAX_FRAME) $error("eth_mac_rgmii: MIN_FRAME must be in 18..MAX_FRAME (got %0d)", MIN_FRAME);
        if (MAX_FRAME < 64 || MAX_FRAME > 2000) $error("eth_mac_rgmii: MAX_FRAME must be in 64..2000 (got %0d)", MAX_FRAME);
        if (CUT_THROUGH == 0 && SF_DEPTH < 2 * MAX_FRAME) $error("eth_mac_rgmii: SF_DEPTH must hold two frames of MAX_FRAME (got %0d)", SF_DEPTH);
    end

    // ---- receive ----
    logic       rx_rst;
    xpm_cdc_sync_rst #(.DEST_SYNC_FF(4), .INIT(1), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0)) u_rxrst (
        .src_rst(rst), .dest_clk(rgmii_rx_clk), .dest_rst(rx_rst));
    logic [1:0] speed_rx;
    xpm_cdc_array_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(1), .WIDTH(2)) u_spd (
        .src_clk(clk), .src_in(speed), .dest_clk(rgmii_rx_clk), .dest_out(speed_rx));
    logic [7:0] g_d;
    logic       g_v, g_dv, g_er;
    rgmii_rx u_rgrx (.rx_clk(rgmii_rx_clk), .speed(speed_rx), .rxd(rgmii_rxd), .rx_ctl(rgmii_rx_ctl), .gmii_d(g_d),
                     .gmii_v(g_v), .gmii_dv(g_dv), .gmii_er(g_er));
    logic       f_v, f_eof, f_er;
    logic [7:0] f_d;
    gmii_cdc u_cdc (.rx_clk(rgmii_rx_clk), .rx_rst(rx_rst), .gmii_d(g_d), .gmii_v(g_v), .gmii_dv(g_dv), .gmii_er(g_er),
                    .clk, .o_v(f_v), .o_eof(f_eof), .o_er(f_er), .o_d(f_d), .o_ovf(rx_fifo_ovf), .o_rxclk_cnt());
    mac_rx #(.MIN_FRAME(MIN_FRAME), .MAX_FRAME(MAX_FRAME)) u_rx (.clk, .rst, .in_valid(f_v), .in_eof(f_eof),
        .in_er(f_er), .in_data(f_d), .sof_pulse(rx_sof_pulse), .out_valid(rx_valid), .out_sof(rx_sof),
        .out_data(rx_data), .out_idx(rx_idx), .end_valid(rx_end_valid), .end_good(rx_end_good),
        .end_fcs_err(rx_end_fcs_err), .end_runt(rx_end_runt), .end_giant(rx_end_giant), .end_er(rx_end_er),
        .end_len(rx_end_len), .ev_bad_pre());
    if (CUT_THROUGH == 0) begin : g_sf
        eth_rx_sf #(.DEPTH(SF_DEPTH)) u_sf (.clk, .rst, .in_valid(rx_valid), .in_sof(rx_sof), .in_data(rx_data),
            .end_valid(rx_end_valid), .end_good(rx_end_good), .end_len(rx_end_len), .m_axis_tdata, .m_axis_tvalid,
            .m_axis_tready, .m_axis_tlast, .ev_dropped(rx_sf_dropped), .ev_overflow(rx_sf_overflow));
    end else begin : g_ct
        assign m_axis_tdata = '0; assign m_axis_tvalid = 1'b0; assign m_axis_tlast = 1'b0;
        assign rx_sf_dropped = 1'b0; assign rx_sf_overflow = 1'b0;
    end

    // ---- transmit ----
    logic        ce, ready, req_valid, last_pulse;
    logic [10:0] req_idx;
    logic [7:0]  t_d, g_txd;
    logic        t_last, bad, g_txen;
    // one beat is taken at each byte time the MAC asks for one; a missing beat is an underrun
    assign s_axis_tready = ce && req_valid && !bad;
    always_ff @(posedge clk) begin
        tx_underrun <= 1'b0;
        if (rst) begin t_d <= '0; t_last <= 1'b0; bad <= 1'b0; end
        else begin
            if (ce && req_valid) begin
                if (bad) begin t_d <= 8'h00; t_last <= 1'b1; end
                else if (s_axis_tvalid) begin
                    t_d <= s_axis_tdata; t_last <= s_axis_tlast;
                    if (s_axis_tuser) bad <= 1'b1;
                end else begin
                    t_d <= 8'h00; t_last <= 1'b1; bad <= 1'b1; tx_underrun <= 1'b1;
                end
            end
            if (last_pulse) bad <= 1'b0;
        end
    end
    mac_tx #(.MIN_DATA(MIN_DATA), .IFG_BYTES(IFG_BYTES)) u_tx (.clk, .rst, .ce, .start(s_axis_tvalid && !bad),
        .ready, .req_idx, .req_valid, .in_data(t_d), .in_last(t_last), .poison(tx_poison || bad), .txd(g_txd),
        .tx_en(g_txen), .first_pulse(tx_first_pulse), .sof_pulse(tx_sof_pulse), .last_pulse(last_pulse),
        .last_poisoned(tx_last_poisoned), .busy());
    assign tx_last_pulse = last_pulse;
    rgmii_tx u_rgtx (.clk, .clk90, .rst, .speed, .ce, .gmii_d(g_txd), .gmii_en(g_txen), .gmii_er(1'b0),
                     .txd(rgmii_txd), .tx_ctl(rgmii_tx_ctl), .txc(rgmii_txc));
endmodule
