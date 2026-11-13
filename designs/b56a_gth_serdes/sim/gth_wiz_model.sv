`timescale 1ns/1ps
// gth_wiz_model.sv: a behavioural STAND-IN for the AMD GT Wizard core `gth_wiz` (same ports), for simulating the fabric around it.
//
// WHY: AMD's own simulation model of the core (UNISIM GTHE4 secureip) has 54,716 instances; the Vivado Simulator on the free
// Basic licence refuses more than 50,000 ("The current Vivado Simulator license tier you have, BASIC, does not meet the
// requirement to run the number of instances in this design"), see results/56a_serdes/licences.md. So the GT itself is not simulated
// here: this model replaces it, and the GT is tested on the board (brief 56B). It is NOT a model of the transceiver:
//   - the serial pins are not modelled: tx data reaches rx data through a word-level loop, three clocks later, once rx is up;
//   - TXUSRCLK2 = RXUSRCLK2 = the reference clock input (the bench drives it at 161.13 MHz); no CDR, no equaliser, no jitter;
//   - the reset helper is a counter: tx_done a fixed time after reset-all or a TX reset, rx_done later;
//   - the PRBS generator/checker model PRBS-7/15/23/31 (selects 1, 3, 4, 5) with TXPRBSFORCEERR, RXPRBSERR and RXPRBSLOCKED;
//   - the DRP is a 1024 x 16 memory that answers after 4 clocks.
// Behaviour that the real core has and this does not: everything analogue, lock times, buffer bypass, loopback modes.
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
    output logic        txpmaresetdone_out
);
    import prbs64_pkg::*;
    localparam int TX_DELAY = 300, RX_DELAY = 700;           // freerun clocks (100 MHz) from the reset to the done flag
    logic clk;
    assign clk = gtrefclk00_in;
    assign gtwiz_userclk_tx_usrclk2_out = clk;  assign gtwiz_userclk_rx_usrclk2_out = clk;
    assign gtwiz_userclk_tx_usrclk_out = clk;   assign gtwiz_userclk_rx_usrclk_out = clk;
    assign gtwiz_userclk_tx_srcclk_out = clk;   assign gtwiz_userclk_rx_srcclk_out = clk;
    assign qpll0outclk_out = clk; assign qpll0outrefclk_out = clk;
    assign gthtxp_out = 1'b0; assign gthtxn_out = 1'b1; assign eyescandataerror_out = 1'b0;

    // reset helper stand-in, counted on the free-running clock
    int txc = 0, rxc = 0;
    logic tx_up = 0, rx_up = 0;
    logic ra, rt, rtd, rr, rrd;
    assign ra = gtwiz_reset_all_in; assign rt = gtwiz_reset_tx_pll_and_datapath_in; assign rtd = gtwiz_reset_tx_datapath_in;
    assign rr = gtwiz_reset_rx_pll_and_datapath_in; assign rrd = gtwiz_reset_rx_datapath_in;
    always_ff @(posedge gtwiz_reset_clk_freerun_in) begin
        if (ra || rt || rtd) begin txc <= 0; tx_up <= 1'b0; end
        else if (txc < TX_DELAY) txc <= txc + 1;
        else tx_up <= 1'b1;
        if (ra || rr || rrd || (ra || rt)) begin rxc <= 0; rx_up <= 1'b0; end
        else if (rxc < RX_DELAY && tx_up) rxc <= rxc + 1;
        else if (rxc >= RX_DELAY) rx_up <= 1'b1;
    end
    assign gtpowergood_out = 1'b1;
    assign txpmaresetdone_out = tx_up || txc > 20;
    assign rxpmaresetdone_out = rx_up || rxc > 20;
    assign gtwiz_userclk_tx_active_out = txpmaresetdone_out;
    assign gtwiz_userclk_rx_active_out = rxpmaresetdone_out;
    assign gtwiz_reset_rx_cdr_stable_out = rx_up || rxc > 100;
    assign rxcdrlock_out = rx_up;
    // done flags in the user clock domains
    logic txd_q = 0, rxd_q = 0;
    always_ff @(posedge clk) begin txd_q <= tx_up; rxd_q <= rx_up; end
    assign gtwiz_reset_tx_done_out = txd_q;
    assign gtwiz_reset_rx_done_out = rxd_q;

    // data path: PRBS generator (hard) or the user data, delayed three words
    logic [30:0] gst = 31'h7FFFFFFF;
    logic [1:0]  gsel;
    logic [63:0] gword, txw, w1, w2, w3;
    logic [94:0] gnx;
    logic        ferr;
    always_comb begin
        case (txprbssel_in)
            4'd1: gsel = 2'd0;  4'd3: gsel = 2'd1;  4'd4: gsel = 2'd2;  default: gsel = 2'd3;
        endcase
        gnx = prbs64_pkg::step(gst, gsel);
    end
    logic [3:0] tsel_q = 0;
    always_ff @(posedge clk) begin
        tsel_q <= txprbssel_in;
        if (txprbssel_in != tsel_q || txprbssel_in == 0) gst <= 31'h7FFFFFFF;
        else gst <= gnx[94:64];
        ferr <= txprbsforceerr_in;
        gword <= gnx[63:0] ^ {63'd0, ferr};
        txw <= (txprbssel_in != 0) ? gword : gtwiz_userdata_tx_in;
        w1 <= txw ^ (txpolarity_in ? '1 : '0); w2 <= w1; w3 <= w2;
    end
    assign gtwiz_userdata_rx_out = rx_up ? (w3 ^ (rxpolarity_in ? '1 : '0)) : 64'd0;

    // hard PRBS checker: lock after 8 error-free words, then report a cycle with any error
    logic [30:0] cst; logic [1:0] csel; logic [63:0] cexp; logic [94:0] cnx; logic [3:0] rsel_q = 0; int cgood = 0; logic clock_q = 0;
    always_comb begin
        case (rxprbssel_in) 4'd1: csel = 2'd0; 4'd3: csel = 2'd1; 4'd4: csel = 2'd2; default: csel = 2'd3; endcase
        cnx = prbs64_pkg::step(cst, csel);
    end
    always_ff @(posedge clk) begin
        rsel_q <= rxprbssel_in; rxprbserr_out <= 1'b0;
        if (rxprbssel_in == 0 || rxprbssel_in != rsel_q || rxprbscntreset_in || !rx_up) begin
            clock_q <= 1'b0; cgood <= 0; cst <= prbs64_pkg::load(gtwiz_userdata_rx_out, csel);
        end else if (!clock_q) begin
            if (cnx[63:0] == gtwiz_userdata_rx_out) begin cgood <= cgood + 1; cst <= cnx[94:64]; if (cgood >= 7) clock_q <= 1'b1; end
            else begin cgood <= 0; cst <= prbs64_pkg::load(gtwiz_userdata_rx_out, csel); end
        end else begin
            cst <= cnx[94:64];
            rxprbserr_out <= (cnx[63:0] != gtwiz_userdata_rx_out);
        end
    end
    assign rxprbslocked_out = clock_q;

    // DRP: a memory answering after four clocks
    logic [15:0] mem [0:1023];
    int dly = 0; logic [9:0] da; logic dw; logic [15:0] ddi;
    always_ff @(posedge drpclk_in) begin
        drprdy_out <= 1'b0;
        if (drpen_in) begin dly <= 4; da <= drpaddr_in; dw <= drpwe_in; ddi <= drpdi_in; end
        else if (dly > 0) begin
            dly <= dly - 1;
            if (dly == 1) begin drprdy_out <= 1'b1; if (dw) mem[da] <= ddi; else drpdo_out <= mem[da]; end
        end
    end
    initial begin for (int i = 0; i < 1024; i++) mem[i] = 16'(i ^ 16'h5A00); end
endmodule
