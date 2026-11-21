#!/usr/bin/env python3
"""Brief 126: gth_wiz_model96e.sv plus a stand-in for the Wizard's buffer-bypass controllers and their eight ports, exactly as results/b96f1b/core_sim.sh makes it (copied from there so this script stands alone).
usage: make_bp_model.py <gth_wiz_model96e.sv> <out.sv>"""
import sys
s = open(sys.argv[1]).read().replace("always_ff @(", "always @(")
s = s.replace("module gth_wiz (", """module gth_wiz (
    input  logic [0:0]  gtwiz_buffbypass_tx_reset_in,
    input  logic [0:0]  gtwiz_buffbypass_tx_start_user_in,
    output logic [0:0]  gtwiz_buffbypass_tx_done_out,
    output logic [0:0]  gtwiz_buffbypass_tx_error_out,
    input  logic [0:0]  gtwiz_buffbypass_rx_reset_in,
    input  logic [0:0]  gtwiz_buffbypass_rx_start_user_in,
    output logic [0:0]  gtwiz_buffbypass_rx_done_out,
    output logic [0:0]  gtwiz_buffbypass_rx_error_out,
    output logic [0:0]  txprgdivresetdone_out,""", 1)
s = s.replace("endmodule", """    // brief 96F1b stand-in of the buffer-bypass controllers (UNCONFIRMED figures): idle -> start on the rising edge of the reset-done level (resetdone_reg is cleared by the controller's reset, so a start also
    // follows the release of a reset while the level is high) -> done BP_CLKS clocks later; the first HANG_TX / HANG_RX starts never finish (the controller waits for SYNCDONE until it is reset)
`ifndef BP_CLKS
 `define BP_CLKS 100
`endif
`ifndef HANG_TX
 `define HANG_TX 0
`endif
`ifndef HANG_RX
 `define HANG_RX 0
`endif
    assign txprgdivresetdone_out = 1'b1;
    logic tx_dn = 0, rx_dn = 0, tx_rd = 0, rx_rd = 0, tx_busy = 0, rx_busy = 0, tx_hung = 0, rx_hung = 0;
    assign gtwiz_buffbypass_tx_done_out = tx_dn; assign gtwiz_buffbypass_rx_done_out = rx_dn;
    assign gtwiz_buffbypass_tx_error_out = 1'b0; assign gtwiz_buffbypass_rx_error_out = 1'b0;
    int tcnt = 0, rcnt = 0, thang = `HANG_TX, rhang = `HANG_RX;
    always @(posedge clk) begin
        if (gtwiz_buffbypass_tx_reset_in) begin tx_dn <= 0; tx_rd <= 0; tx_busy <= 0; tx_hung <= 0; tcnt <= 0; end
        else begin
            tx_rd <= gtwiz_reset_tx_done_out;
            if (!tx_busy && gtwiz_reset_tx_done_out && !tx_rd) begin
                tx_busy <= 1; tx_dn <= 0; tcnt <= 0;
                if (thang > 0) begin thang = thang - 1; tx_hung <= 1; end
            end else if (tx_busy && !tx_hung) begin
                tcnt <= tcnt + 1;
                if (tcnt == 5 + `BP_CLKS) begin tx_dn <= 1; tx_busy <= 0; end
            end
        end
    end
    always @(posedge rxclk) begin
        if (gtwiz_buffbypass_rx_reset_in) begin rx_dn <= 0; rx_rd <= 0; rx_busy <= 0; rx_hung <= 0; rcnt <= 0; end
        else begin
            rx_rd <= gtwiz_reset_rx_done_out;
            if (!rx_busy && gtwiz_reset_rx_done_out && !rx_rd) begin
                rx_busy <= 1; rx_dn <= 0; rcnt <= 0;
                if (rhang > 0) begin rhang = rhang - 1; rx_hung <= 1; end
            end else if (rx_busy && !rx_hung) begin
                rcnt <= rcnt + 1;
                if (rcnt == 5 + `BP_CLKS) begin rx_dn <= 1; rx_busy <= 0; end
            end
        end
    end
endmodule""")
open(sys.argv[2], "w").write(s)
