#!/bin/bash
# Brief 96F1b: the whole variant core (rm_gp_bypass: RATE_MATCH 1, RM_OWN 1) in xsim 2026.1 with AMD's real XPM macros, as results/b96f1/core_sim.sh, now with the reset synchroniser and the alignment
# timeout/retry (rtl/gt_bp_ctl.sv) in the core. STAND-IN transceiver with the bypass controllers' ports: a behavioural controller that starts on the rising edge of the reset-done level (or on the first
# clock after its own reset is released while that level is high, as the Wizard's controller does), is done BP_CLKS clocks later, and can be made to hang (ignore its first N starts) to exercise the retry.
# The real alignment time and the latency saving are NOT simulated (the whole point of the board test). Scenarios (name: BP_CLKS, hang TX, hang RX, timeout clocks, retries):
#   normal: 100 clocks, no hang (the same measurement as 96F1: link up, 8 orders, tick-to-trade)
#   retry:  100 clocks, one hung start per side, timeout 3000 clocks, 2 retries: link up after one retry; GT_BUF shows retries = 1 and gave-up = 0
#   giveup: every start hangs, timeout 1500 clocks, 2 retries: the link never comes up; GT_BUF shows retries = 2 and gave-up = 1 (set, and seen)
#   results/b96f1b/core_sim.sh [scenario list, default "normal retry giveup"]     simulation only: no heavy slot while load is under 6 and more than 12 GB is free
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; D=designs/b96_kr260_10g; R=$ROOT/$D/rtl; V=$ROOT/$D/rm_gp_bypass
WORK="${WORK:-$ROOT/build/core_sim96f1b}"; mkdir -p "$WORK"; cd "$WORK"
set +u; source /opt/Xilinx/2026.1/Vivado/settings64.sh >/dev/null 2>&1; set -u
SCEN="${*:-normal retry giveup}"
mkdir -p rtl_x; for f in "$R"/*.sv "$V"/rtl/*.sv; do sed -e 's/always_ff @(/always @(/' -e 's/INIT_SYNC_FF(0)/INIT_SYNC_FF(1)/' "$f" > rtl_x/$(basename "$f"); done   # rm_gp_bypass/rtl/b96_core.sv overwrites the base core (same name, listed last)
for f in tb_lat_core; do sed 's/always_ff @(/always @(/' "$ROOT/$D/sim/$f.sv" > rtl_x/$f.sv; done
python3 - "$WORK" <<'PY'
import sys
w = sys.argv[1]
t = open(f"{w}/rtl_x/tb_lat_core.sv").read()
rd = ('hr(12\'h008, st); $display("UP FEATURES %h", st);\n        hr(12\'h020, st); $display("UP GT_BUF %h", st);\n        hr(12\'h014, st); $display("UP GTSTAT %h", st);')
t = t.replace('$display("LINK UP at %0t", $time);', '$display("LINK UP at %0t", $time);\n        ' + rd, 1)
t = t.replace('$display("LINK DID NOT COME UP: GTSTAT %h", st); $finish;', '$display("LINK DID NOT COME UP: GTSTAT %h", st); ' + rd.replace("UP ", "NOLINK ") + ' $finish;', 1)
t = t.replace("b96_core #(.BUILD_STAMP(32'h96),", "b96_core #(.BP_TX_TO(`BPTO), .BP_RX_TO(`BPTO), .BP_RETRIES(`BPRTY), .BUILD_STAMP(32'h96),", 1)
open(f"{w}/rtl_x/tb_lat_core.sv", "w").write(t)
PY
python3 - "$ROOT/$D/sim/gth_wiz_model96e.sv" "$WORK/rtl_x/gth_wiz_model96f1b.sv" <<'PY'
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
PY
SRCS="rtl_x/b96_pkg.sv rtl_x/pcs_tx.sv rtl_x/pcs_rx.sv rtl_x/mac64_tx.sv rtl_x/mac64_rx.sv rtl_x/hs_vec.sv rtl_x/frame_src.sv rtl_x/trade64.sv rtl_x/rate_match.sv rtl_x/rate_match_gp.sv rtl_x/tx_path.sv rtl_x/rx_path.sv rtl_x/rx_path_legacy.sv rtl_x/gt_bp_gate.sv rtl_x/gt_bp_ctl.sv rtl_x/b96_core.sv"
for sc in $SCEN; do
  case "$sc" in
    normal) bp=100; ht=0;  hr=0;  to=4833984; ry=3;;
    retry)  bp=100; ht=1;  hr=1;  to=3000;    ry=2;;
    giveup) bp=100; ht=99; hr=99; to=1500;    ry=2;;
    *) echo "unknown scenario $sc"; continue;;
  esac
  mkdir -p "$sc"; ( cd "$sc" && xvlog -sv -L xpm -d RXPH=0.0 -d BP_CLKS=$bp -d HANG_TX=$ht -d HANG_RX=$hr -d BPTO=$to -d BPRTY=$ry $(for f in $SRCS; do echo ../$f; done) ../rtl_x/gth_wiz_model96f1b.sv ../rtl_x/tb_lat_core.sv "$XILINX_VIVADO/data/verilog/src/glbl.v" > xvlog.log 2>&1 \
    && xelab -L xpm -L unisims_ver -debug off -generic_top "RATE_MATCH=1" -generic_top "RM_OWN=1" -generic_top "RM_DIRECT=0" tb_lat_core work.glbl -s s > xelab.log 2>&1 && xsim s -R > xsim.log 2>&1 )
  grep -E "^(ORD|DONE|TIMEOUT|LINK|UP |NOLINK|ID|FEATURES|GTSTAT)" "$sc/xsim.log" > "out_$sc.log"
  echo "$sc: $(grep -c ^ORD out_$sc.log) orders; $(grep -E 'DONE|TIMEOUT|LINK|UP |NOLINK' out_$sc.log | tr '\n' ' ')"
done
