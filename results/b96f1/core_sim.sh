#!/bin/bash
# Brief 96F1: the whole variant core (rm_gp_bypass: RATE_MATCH 1, RM_OWN 1) in xsim 2026.1 with AMD's real XPM macros, the same testbench and the same measurement as results/b96e/core_lat_sim.sh, with a
# STAND-IN transceiver that has the bypass controllers' ports. The stand-in is sim/gth_wiz_model96e.sv plus a behavioural controller: after the rising edge of each reset-done level the controller's done output
# (and error, always 0) is cleared 5 clocks later and raised again BP_CLKS clocks after that (the real alignment time is NOT known: UNCONFIRMED), so the gate, the status bits and the link bring-up are
# exercised; the stand-in has no buffers, so it can say NOTHING about the latency that bypassing them removes (the whole point of the board test).
#   results/b96f1/core_sim.sh [BP_CLKS list, default "100 2000"]        simulation only: no heavy slot while load is under 6 and more than 12 GB is free
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; D=designs/b96_kr260_10g; R=$ROOT/$D/rtl; V=$ROOT/$D/rm_gp_bypass
WORK="${WORK:-$ROOT/build/core_sim96f1}"; mkdir -p "$WORK"; cd "$WORK"
set +u; source /opt/Xilinx/2026.1/Vivado/settings64.sh >/dev/null 2>&1; set -u
BPS="${*:-100 2000}"
# xsim needs the always_ff -> always and INIT_SYNC_FF 0 -> 1 copy, as in results/b96e/core_lat_sim.sh (the rtl files themselves are not touched)
mkdir -p rtl_x; for f in "$R"/*.sv "$V"/rtl/*.sv; do sed -e 's/always_ff @(/always @(/' -e 's/INIT_SYNC_FF(0)/INIT_SYNC_FF(1)/' "$f" > rtl_x/$(basename "$f"); done   # rm_gp_bypass/rtl/b96_core.sv overwrites the base core (same name, listed last)
for f in tb_lat_core; do sed 's/always_ff @(/always @(/' "$ROOT/$D/sim/$f.sv" > rtl_x/$f.sv; done
# the testbench with two more reads after the link is up: FEATURES (bit 6) and GT_BUF (bits 15:10)
python3 - "$WORK" <<'PY'
import sys, re
w = sys.argv[1]
t = open(f"{w}/rtl_x/tb_lat_core.sv").read()
t = t.replace('$display("LINK UP at %0t", $time);', '$display("LINK UP at %0t", $time);\n        hr(12\'h008, st); $display("UP FEATURES %h", st);\n        hr(12\'h020, st); $display("UP GT_BUF %h", st);\n        hr(12\'h014, st); $display("UP GTSTAT %h", st);', 1)
open(f"{w}/rtl_x/tb_lat_core.sv", "w").write(t)
PY
python3 - "$ROOT/$D/sim/gth_wiz_model96e.sv" "$WORK/rtl_x/gth_wiz_model96f1.sv" <<'PY'
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
s = s.replace("endmodule", """    // brief 96F1 stand-in of the buffer-bypass controllers: start 3 clocks after the rising edge of the reset-done level, done low 5 clocks after that edge, high BP_CLKS clocks later (UNCONFIRMED figures)
`ifndef BP_CLKS
 `define BP_CLKS 100
`endif
    assign txprgdivresetdone_out = 1'b1;
    logic tx_dn = 0, rx_dn = 0;
    assign gtwiz_buffbypass_tx_done_out = tx_dn; assign gtwiz_buffbypass_rx_done_out = rx_dn;
    assign gtwiz_buffbypass_tx_error_out = 1'b0; assign gtwiz_buffbypass_rx_error_out = 1'b0;
    int tcnt = 0, rcnt = 0; logic txd_p = 0, rxd_p = 0;
    always @(posedge clk) begin
        txd_p <= gtwiz_reset_tx_done_out;
        if (gtwiz_buffbypass_tx_reset_in) begin tx_dn <= 0; tcnt <= 0; end
        else begin
            if (gtwiz_reset_tx_done_out && !txd_p) tcnt <= 1;
            else if (tcnt != 0 && tcnt < 5 + `BP_CLKS) tcnt <= tcnt + 1;
            if (tcnt == 5) tx_dn <= 0;
            if (tcnt == 5 + `BP_CLKS) tx_dn <= 1;
            if (!gtwiz_reset_tx_done_out) tcnt <= 0;
        end
    end
    always @(posedge rxclk) begin
        rxd_p <= gtwiz_reset_rx_done_out;
        if (gtwiz_buffbypass_rx_reset_in) begin rx_dn <= 0; rcnt <= 0; end
        else begin
            if (gtwiz_reset_rx_done_out && !rxd_p) rcnt <= 1;
            else if (rcnt != 0 && rcnt < 5 + `BP_CLKS) rcnt <= rcnt + 1;
            if (rcnt == 5) rx_dn <= 0;
            if (rcnt == 5 + `BP_CLKS) rx_dn <= 1;
            if (!gtwiz_reset_rx_done_out) rcnt <= 0;
        end
    end
endmodule""")
open(sys.argv[2], "w").write(s)
PY
SRCS="rtl_x/b96_pkg.sv rtl_x/pcs_tx.sv rtl_x/pcs_rx.sv rtl_x/mac64_tx.sv rtl_x/mac64_rx.sv rtl_x/hs_vec.sv rtl_x/frame_src.sv rtl_x/trade64.sv rtl_x/rate_match.sv rtl_x/rate_match_gp.sv rtl_x/tx_path.sv rtl_x/rx_path.sv rtl_x/rx_path_legacy.sv rtl_x/gt_bp_gate.sv rtl_x/b96_core.sv"
for bp in $BPS; do
  mkdir -p "bp$bp"; ( cd "bp$bp" && xvlog -sv -L xpm -d RXPH=0.0 -d BP_CLKS=$bp $(for f in $SRCS; do echo ../$f; done) ../rtl_x/gth_wiz_model96f1.sv ../rtl_x/tb_lat_core.sv "$XILINX_VIVADO/data/verilog/src/glbl.v" > xvlog.log 2>&1 \
    && xelab -L xpm -L unisims_ver -debug off -generic_top "RATE_MATCH=1" -generic_top "RM_OWN=1" -generic_top "RM_DIRECT=0" tb_lat_core work.glbl -s s > xelab.log 2>&1 && xsim s -R > xsim.log 2>&1 )
  grep -E "^(ORD|DONE|TIMEOUT|LINK|UP |ID|FEATURES|GTSTAT)" "bp$bp/xsim.log" > "out_bp$bp.log"
  echo "BP_CLKS $bp: $(grep -c ^ORD out_bp$bp.log) orders; $(grep -E 'DONE|TIMEOUT|LINK|UP ' out_bp$bp.log | tr '\n' ' ')"
done
