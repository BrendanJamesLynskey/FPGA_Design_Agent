`timescale 1ns/1ps
// gth_wiz_model96.sv: a behavioural STAND-IN for the AMD GT Wizard core `gth_wiz` (same ports as designs/b56a_gth_serdes/sim/gth_wiz_model.sv)
// for simulating brief 96's fabric around it. The real GTHE4 simulation model is refused by the Basic Vivado Simulator (54,716 instances
// against a limit of 50,000: results/56a_serdes/licences.md), so the transceiver itself is NOT simulated; it is tested on the board.
// What this model does: carries the 64-bit TX words to the RX words through a bit-level channel of a chosen bit offset (BIT_OFFSET: where the
// receiver's word boundary falls against the sender's), with a fixed word delay; both user clocks are the reference input (the bench drives
// it at 161.1328125 MHz); the reset helper is a counter; RX data is zero in normal mode when TX_LINK is 0. Not modelled: CDR, equaliser,
// jitter, the elastic buffer, the two separate user clocks, loopback modes (the loop is always closed), optics.
// Brief 96D adds a DRP STAND-IN: a 1024 x 16 register file that answers DRDY three clocks after DRPEN, and a stand-in of the eye-scan state machine of
// UG576 Figure 4-21 (WAIT, RESET, COUNT, END) at the real DRP addresses (UG576 v1.7.1 appendix C: 0x3C ES_CONTROL/ES_PRESCALE, 0x4F ES_HORZ_OFFSET, 0x97
// RX_EYESCAN_VS_*, 0x251 es_error_count, 0x252 es_sample_count, 0x253 es_control_status). Its error count is NOT a physical eye: it is a fixed mixing
// function of the offsets (ES_FN below, mirrored by model/eyescan.py `stand_in_error_count`) with a different weight per field, so a test can show that each
// field written by the sequencer reached the right bit of the right word and that the read-modify-write kept the neighbours. It says nothing about the GT.
module gth_wiz (
    input  logic        gtwiz_userclk_tx_reset_in,
    output logic        gtwiz_userclk_tx_srcclk_out,
    output logic        gtwiz_userclk_tx_usrclk_out,
    output logic        gtwiz_userclk_tx_usrclk2_out,
    output logic        gtwiz_userclk_tx_active_out,
    input  logic        gtwiz_userclk_rx_reset_in,
    output logic        gtwiz_userclk_rx_srcclk_out,
    output logic        gtwiz_userclk_rx_usrclk_out,
    output logic        gtwiz_userclk_rx_usrclk2_out,
    output logic        gtwiz_userclk_rx_active_out,
    input  logic        gtwiz_reset_clk_freerun_in,
    input  logic        gtwiz_reset_all_in,
    input  logic        gtwiz_reset_tx_pll_and_datapath_in,
    input  logic        gtwiz_reset_tx_datapath_in,
    input  logic        gtwiz_reset_rx_pll_and_datapath_in,
    input  logic        gtwiz_reset_rx_datapath_in,
    output logic        gtwiz_reset_rx_cdr_stable_out,
    output logic        gtwiz_reset_tx_done_out,
    output logic        gtwiz_reset_rx_done_out,
    input  logic [63:0] gtwiz_userdata_tx_in,
    output logic [63:0] gtwiz_userdata_rx_out,
    input  logic        gtrefclk00_in,
    output logic        qpll0outclk_out,
    output logic        qpll0outrefclk_out,
    input  logic [9:0]  drpaddr_in,
    input  logic        drpclk_in,
    input  logic [15:0] drpdi_in,
    input  logic        drpen_in,
    input  logic        drpwe_in,
    input  logic        eyescanreset_in,
    input  logic        eyescantrigger_in,
    input  logic        gthrxn_in,
    input  logic        gthrxp_in,
    input  logic [2:0]  loopback_in,
    input  logic        rxcdrhold_in,
    input  logic        rxdfelpmreset_in,
    input  logic        rxlpmen_in,
    input  logic        rxpolarity_in,
    input  logic        rxprbscntreset_in,
    input  logic [3:0]  rxprbssel_in,
    input  logic [4:0]  txdiffctrl_in,
    input  logic        txelecidle_in,
    input  logic        txpippmen_in,
    input  logic        txpippmsel_in,
    input  logic [4:0]  txpippmstepsize_in,
    input  logic        txpolarity_in,
    input  logic [4:0]  txpostcursor_in,
    input  logic        txprbsforceerr_in,
    input  logic [3:0]  txprbssel_in,
    input  logic [4:0]  txprecursor_in,
    output logic [15:0] drpdo_out,
    output logic        drprdy_out,
    output logic        eyescandataerror_out,
    output logic        gthtxn_out,
    output logic        gthtxp_out,
    output logic        gtpowergood_out,
    output logic        rxcdrlock_out,
    output logic        rxpmaresetdone_out,
    output logic        rxprbserr_out,
    output logic        rxprbslocked_out,
    output logic        txpmaresetdone_out,
    output logic [1:0]  txbufstatus_out,
    output logic [2:0]  rxbufstatus_out
);
    parameter int BIT_OFFSET = 0;
    localparam int TX_DELAY = 300, RX_DELAY = 700;
    logic clk;
    assign clk = gtrefclk00_in;
    assign gtwiz_userclk_tx_usrclk2_out = clk;  assign gtwiz_userclk_rx_usrclk2_out = clk;
    assign gtwiz_userclk_tx_usrclk_out = clk;   assign gtwiz_userclk_rx_usrclk_out = clk;
    assign gtwiz_userclk_tx_srcclk_out = clk;   assign gtwiz_userclk_rx_srcclk_out = clk;
    assign qpll0outclk_out = clk; assign qpll0outrefclk_out = clk;
    assign gthtxp_out = 1'b0; assign gthtxn_out = 1'b1; assign eyescandataerror_out = 1'b0;
    assign rxprbserr_out = 1'b0; assign rxprbslocked_out = 1'b0;
    int txc = 0, rxc = 0;
    logic tx_up = 0, rx_up = 0;
    logic ra, rt, rtd, rr, rrd;
    assign ra = gtwiz_reset_all_in; assign rt = gtwiz_reset_tx_pll_and_datapath_in; assign rtd = gtwiz_reset_tx_datapath_in;
    assign rr = gtwiz_reset_rx_pll_and_datapath_in; assign rrd = gtwiz_reset_rx_datapath_in;
    always_ff @(posedge gtwiz_reset_clk_freerun_in) begin
        if (ra || rt || rtd) begin txc <= 0; tx_up <= 1'b0; end
        else if (txc < TX_DELAY) txc <= txc + 1;
        else tx_up <= 1'b1;
        if (ra || rr || rrd || rt) begin rxc <= 0; rx_up <= 1'b0; end
        else if (rxc < RX_DELAY && tx_up) rxc <= rxc + 1;
        else if (rxc >= RX_DELAY) rx_up <= 1'b1;
    end
    assign gtpowergood_out = 1'b1;
    assign txbufstatus_out = 2'b00; assign rxbufstatus_out = 3'b000;
    assign txpmaresetdone_out = tx_up || txc > 20;
    assign rxpmaresetdone_out = rx_up || rxc > 20;
    assign gtwiz_userclk_tx_active_out = txpmaresetdone_out;
    assign gtwiz_userclk_rx_active_out = rxpmaresetdone_out;
    assign gtwiz_reset_rx_cdr_stable_out = rx_up || rxc > 100;
    assign rxcdrlock_out = rx_up;
    logic txd_q = 0, rxd_q = 0;
    always_ff @(posedge clk) begin txd_q <= tx_up; rxd_q <= rx_up; end
    assign gtwiz_reset_tx_done_out = txd_q;
    assign gtwiz_reset_rx_done_out = rxd_q;
    // channel: the sender's bit stream delayed by two words, shifted by BIT_OFFSET bits
    logic [63:0] w1 = '0, w2 = '0, w3 = '0;
    logic [127:0] win;
    assign win = {w1, w2} >> BIT_OFFSET;
    always_ff @(posedge clk) begin w1 <= gtwiz_userdata_tx_in; w2 <= w1; w3 <= w2; end
    logic [63:0] corrupt_xor = '0;      // set by the bench (hierarchically) to flip bits of the next received word
    assign gtwiz_userdata_rx_out = win[63:0] ^ corrupt_xor;
    // ---- DRP stand-in (brief 96D)
    logic [15:0] drp_mem [0:1023];
    logic [1:0]  es_state;           // 0 WAIT(000), 1 RESET(001), 2 COUNT(011), 3 END(010)
    logic [15:0] es_err, es_samp;
    logic        drp_dead = 1'b0;    // set by a test: the DRP never answers (DRDY stays low)
    logic        es_hold = 1'b0;     // set by a test (hierarchically) to keep the stand-in in COUNT, so the sequencer's poll times out
    int          es_cnt = 0;
    int          drp_dly = 0;
    logic        drp_pend = 0, drp_pend_we = 0;
    logic [9:0]  drp_pend_a;
    logic [15:0] drp_pend_d;
    logic        drprdy_r = 0;
    logic [15:0] drpdo_r = 16'h0;
    assign drprdy_out = drprdy_r;
    assign drpdo_out = drpdo_r;
    initial begin
        for (int i = 0; i < 1024; i++) drp_mem[i] = 16'h0;
        drp_mem[10'h03C] = 16'h0360;      // ES_EYE_SCAN_EN and ES_ERRDET_EN set by the build (bits 9, 8), bits 7:5 = 011 as a neighbour that must survive
        drp_mem[10'h04F] = 16'h0005;      // ES_HORZ_OFFSET 0, FTS_LANE_DESKEW_CFG = 5 (a neighbour that must survive)
        drp_mem[10'h097] = 16'h1800;      // RX_AFE_CM_EN and RX_CAPFF_SARC_ENB set (neighbours that must survive)
        es_state = 2'd0; es_err = 16'h0; es_samp = 16'h0;
    end
    // the mixing function of the stand-in (mirrored in model/eyescan.py)
    function automatic logic [15:0] es_fn(input logic [11:0] horz, input logic [6:0] code, input logic neg, input logic ut, input logic [1:0] rng, input logic [4:0] pre);
        logic signed [11:0] h;
        logic [31:0] v;
        h = horz;
        v = 32'(int'(h) * int'(h)) * 32'd7 + 32'(code) * 32'd13 + 32'(neg) * 32'd101 + 32'(ut) * 32'd211 + 32'(rng) * 32'd307 + 32'(pre) * 32'd401;
        return v[15:0];
    endfunction
    always_ff @(posedge drpclk_in) begin
        drprdy_r <= 1'b0;
        if (drpen_in && !drp_pend) begin drp_pend <= 1'b1; drp_dly <= 3; drp_pend_we <= drpwe_in; drp_pend_a <= drpaddr_in; drp_pend_d <= drpdi_in; end
        else if (drp_pend) begin
            if (drp_dead) begin end
            else if (drp_dly == 0) begin
                drp_pend <= 1'b0; drprdy_r <= 1'b1;
                if (drp_pend_we) begin
                    drp_mem[drp_pend_a] <= drp_pend_d;
                    if (drp_pend_a == 10'h03C) begin
                        if (drp_pend_d[10]) begin if (es_state == 2'd0) begin es_state <= 2'd1; es_cnt <= 0; end end
                        else es_state <= 2'd0;
                    end
                end else begin
                    case (drp_pend_a)
                        10'h251: drpdo_r <= es_err;
                        10'h252: drpdo_r <= es_samp;
                        10'h253: drpdo_r <= {12'h0, (es_state == 2'd0) ? 4'b0001 : (es_state == 2'd1) ? 4'b0010 : (es_state == 2'd2) ? 4'b0110 : 4'b0101};
                        default: drpdo_r <= drp_mem[drp_pend_a];
                    endcase
                end
            end else drp_dly <= drp_dly - 1;
        end
        case (es_state)
            2'd1: begin es_state <= 2'd2; es_cnt <= 0; end
            2'd2: begin
                es_cnt <= es_cnt + 1;
                if (es_cnt == 24 && !es_hold) begin
                    es_state <= 2'd3;
                    es_samp <= 16'hFFFF;
                    es_err <= es_fn(drp_mem[10'h04F][15:4], drp_mem[10'h097][8:2], drp_mem[10'h097][10], drp_mem[10'h097][9], drp_mem[10'h097][1:0], drp_mem[10'h03C][4:0]);
                end
            end
            default: ;
        endcase
    end
endmodule
