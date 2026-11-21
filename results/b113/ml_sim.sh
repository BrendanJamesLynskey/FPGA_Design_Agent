#!/bin/bash
# Brief 113: the whole core in xsim 2026.1 with AMD's real XPM macros and a synthetic feed injected on the receive words (designs/b96_kr260_10g/rm_gp_ml/sim/tb_ml_core.sv).
# usage: [LOOP=<n frames>] ml_sim.sh <build: ml | base> <stream dir (words.hex, expect.json); ignored with LOOP> <veto 0|1> <phase_ps> <hold> <out log>
#   build ml   = rm_gp_ml (the ML stage; <hold> = trade64's simulation-only ML_HOLD: 0 in every real build, 1 or 2 to show what a class made after the message would cost)
#   build base = the unmodified rm_gp core (RATE_MATCH 1, RM_OWN 1) with the same stimulus: the control "without the ML stage"
# Simulation only: no heavy slot while the load is under 6 and more than 12 GB is free. The rtl is compiled from a copy with always_ff turned into always and INIT_SYNC_FF 0 -> 1 (as results/b96e/core_lat_sim.sh:
# xsim refuses `initial` beside `always_ff`, and the real macros start X with INIT_SYNC_FF 0); the rtl files themselves are not touched.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; D=designs/b96_kr260_10g
BUILD="$1"; STREAM="$2"; VETO="$3"; PH="$4"; HOLD="$5"; LOG="$6"
WORK="${WORK:-$ROOT/build/ml113}/${BUILD}_v${VETO}_p${PH}_h${HOLD}_$(basename "$STREAM")"; mkdir -p "$WORK"; cd "$WORK"
set +u; source /opt/Xilinx/2026.1/Vivado/settings64.sh >/dev/null 2>&1; set -u
mkdir -p rtl_x
R0=$ROOT/$D/rtl; V=$ROOT/$D/rm_gp_ml
cp_x() { sed -e 's/always_ff @(/always @(/' -e 's/INIT_SYNC_FF(0)/INIT_SYNC_FF(1)/' "$1" > rtl_x/$(basename "$1"); }
for f in b96_pkg pcs_tx pcs_rx mac64_tx mac64_rx hs_vec frame_src rate_match rate_match_gp tx_path; do cp_x $R0/$f.sv; done
if [ "$BUILD" = ml ]; then
  for f in ml_pkg ml_stage trade64 rx_path rx_path_legacy b96_core; do cp_x $V/rtl/$f.sv; done
  cp_x $ROOT/designs/b87_ml_trading/rtl/gen/gbt_comb.sv
  cp_x $V/sim/gth_wiz_model113.sv; cp_x $V/sim/tb_ml_core.sv
  SRCS="rtl_x/b96_pkg.sv rtl_x/ml_pkg.sv rtl_x/pcs_tx.sv rtl_x/pcs_rx.sv rtl_x/mac64_tx.sv rtl_x/mac64_rx.sv rtl_x/hs_vec.sv rtl_x/frame_src.sv rtl_x/gbt_comb.sv rtl_x/ml_stage.sv rtl_x/trade64.sv rtl_x/rate_match.sv rtl_x/rate_match_gp.sv rtl_x/tx_path.sv rtl_x/rx_path.sv rtl_x/rx_path_legacy.sv rtl_x/b96_core.sv rtl_x/gth_wiz_model113.sv rtl_x/tb_ml_core.sv"
  DEFS="-d ML=1 ${EXTRA_DEFS:-}"
else
  for f in trade64 rx_path rx_path_legacy b96_core; do cp_x $R0/$f.sv; done
  cp_x $V/sim/gth_wiz_model113.sv; cp_x $V/sim/tb_ml_core.sv
  SRCS="rtl_x/b96_pkg.sv rtl_x/pcs_tx.sv rtl_x/pcs_rx.sv rtl_x/mac64_tx.sv rtl_x/mac64_rx.sv rtl_x/hs_vec.sv rtl_x/frame_src.sv rtl_x/trade64.sv rtl_x/rate_match.sv rtl_x/rate_match_gp.sv rtl_x/tx_path.sv rtl_x/rx_path.sv rtl_x/rx_path_legacy.sv rtl_x/b96_core.sv rtl_x/gth_wiz_model113.sv rtl_x/tb_ml_core.sv"
  DEFS=""
fi
ns=$(python3 -c "print($PH/1000.0)")
xvlog -sv -L xpm -d RXPH=$ns $DEFS $SRCS "$XILINX_VIVADO/data/verilog/src/glbl.v" > xvlog.log 2>&1 || { echo "xvlog failed (see $WORK/xvlog.log)"; tail -20 xvlog.log; exit 1; }
xelab -L xpm -L unisims_ver -debug off -generic_top "ML_HOLD=$HOLD" tb_ml_core work.glbl -s s > xelab.log 2>&1 || { echo "xelab failed"; tail -20 xelab.log; exit 1; }
if [ -n "${LOOP:-}" ]; then      # the board's own stream: <LOOP> generator feed frames through the near-end loop, no injection (instrument 1, threshold 9975, as the board script)
  xsim s -R -testplusarg "LOOP=$LOOP" -testplusarg "VETO=$VETO" -testplusarg "INST=1" -testplusarg "THR=9975" > xsim.log 2>&1
else
  NW=$(wc -l < "$STREAM/words.hex")
  xsim s -R -testplusarg "WORDS=$STREAM/words.hex" -testplusarg "NW=$NW" -testplusarg "VETO=$VETO" -testplusarg "INST=${INST:-3}" -testplusarg "THR=${THR:-10002}" > xsim.log 2>&1
fi
grep -E "^(MSG|FIRE|ORD|REG|MLV|ML_ID|ID|FEATURES|GTSTAT|DONE|LINK|NO |TIMEOUT|DIRECT|DBG)" xsim.log > "$LOG"
echo "$BUILD veto $VETO phase_ps $PH hold $HOLD: $(grep -c '^MSG' "$LOG") MSG lines, $(grep -c '^ORD' "$LOG") ORD, $(grep -E '^(DONE|LINK)' "$LOG" | tr '\n' ' ')"
