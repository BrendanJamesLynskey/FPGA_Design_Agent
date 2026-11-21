#!/bin/bash
# Brief 126: the whole core in xsim 2026.1 with AMD's real XPM macros (as 96E, 96F1, 96F1b did), for the build lat_all3_bypass and the builds it is compared with.
#   Cases (name: files, generics):
#     all3          97C's lat_all3 (rtl/b96_core.sv + lat_all3's trade64.sv and tx_path.sv; RATE_MATCH 0, GO_REG 0), GT stand-in with no buffers and no bypass ports
#     all3_bypass   this brief's build: the same two files + rm_gp_bypass's core, gt_bp_gate.sv, gt_bp_ctl.sv; RATE_MATCH 0, GO_REG 0; stand-in transceiver WITH the buffer-bypass controllers' ports
#     rm_gp_bypass  96F1b's build (RATE_MATCH 1, RM_OWN 1, base trade64/tx_path) for the comparison
#     control       the default build (RATE_MATCH 0, GO_REG 1, base files, base core) for the comparison
#   Phases: the receive clock lags the transmit clock by 0, 1550, 3100, 4650 ps (the paths with a crossing depend on it). Bypass scenarios for all3_bypass (BP_CLKS, hang TX, hang RX, timeout clocks, retries):
#     normal 100 clocks no hang / retry one hung start per side, timeout 3000, 2 retries / giveup every start hangs, timeout 1500, 2 retries (as results/b96f1b/core_sim.sh)
#   usage: results/b126/core_sim.sh [cases, default "all3 all3_bypass rm_gp_bypass control"]    SCEN="normal retry giveup" for the bypass scenarios (phase 0 only for retry/giveup)
#   Output: results/b126/core_sim/<case>/ord_<rm>_<own>_<phase>.log and bypass_<scenario>.log, then core_lat.py reduces them (core_sim/<case>.json) with the 96E definitions.
#   Simulation only: no heavy slot needed while load is under 6 and more than 12 GB is free. The stand-in transceiver has NO elastic buffers: the bypass's latency saving cannot appear here.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; D=designs/b96_kr260_10g; R=$ROOT/$D/rtl; B=$ROOT/$D/rm_gp_bypass/rtl; V=$ROOT/$D/lat_all3/rtl; H=$ROOT/results/b126
WORK="${WORK:-$ROOT/build/core_sim126}"; mkdir -p "$WORK" "$H/core_sim"; cd "$WORK"
set +u; source /opt/Xilinx/2026.1/Vivado/settings64.sh >/dev/null 2>&1; set -u
CASES="${*:-all3 all3_bypass rm_gp_bypass control}"; PHASES="${PHASES:-0 1550 3100 4650}"; SCEN="${SCEN:-normal retry giveup}"
conv() { sed -e 's/always_ff @(/always @(/' -e 's/INIT_SYNC_FF(0)/INIT_SYNC_FF(1)/' "$1" > "$2/$(basename "$1")"; }   # xsim refuses always_ff beside an initial; INIT_SYNC_FF only matters in simulation (as 96E)
python3 "$H/make_bp_model.py" "$ROOT/$D/sim/gth_wiz_model96e.sv" "$WORK/gth_wiz_model126bp.sv"
for c in $CASES; do
  case "$c" in
    all3)         rm_=0; own=0; goreg=0; bp=0; files="$R $V";;     # files: the base directory, then the directory whose files replace it
    all3_bypass)  rm_=0; own=0; goreg=0; bp=1; files="$R $V $B";;
    rm_gp_bypass) rm_=1; own=1; goreg=1; bp=1; files="$R $B";;
    control)      rm_=0; own=0; goreg=1; bp=0; files="$R";;
    *) echo "unknown case $c"; continue;;
  esac
  X="$WORK/x_$c"; rm -rf "$X"; mkdir -p "$X"; for d in $files; do for f in "$d"/*.sv; do conv "$f" "$X"; done; done      # later directories overwrite earlier files of the same name
  python3 "$H/make_tb.py" "$ROOT/$D/sim/tb_lat_core.sv" "$X/tb_lat_core126.sv" $bp
  if [ $bp = 1 ]; then cp gth_wiz_model126bp.sv "$X/gth_wiz_model.sv"; else sed 's/always_ff @(/always @(/' "$ROOT/$D/sim/gth_wiz_model96e.sv" > "$X/gth_wiz_model.sv"; fi
  SRCS="b96_pkg.sv pcs_tx.sv pcs_rx.sv mac64_tx.sv mac64_rx.sv hs_vec.sv frame_src.sv trade64.sv rate_match.sv rate_match_gp.sv tx_path.sv rx_path.sv rx_path_legacy.sv b96_core.sv"
  [ $bp = 1 ] && SRCS="b96_pkg.sv pcs_tx.sv pcs_rx.sv mac64_tx.sv mac64_rx.sv hs_vec.sv frame_src.sv trade64.sv rate_match.sv rate_match_gp.sv tx_path.sv rx_path.sv rx_path_legacy.sv gt_bp_gate.sv gt_bp_ctl.sv b96_core.sv"
  OUT="$H/core_sim/$c"; mkdir -p "$OUT"
  run() {   # name, phase ps, BP_CLKS, hang tx, hang rx, timeout, retries
    local t="$1" ph="$2" w="$X/r_$1"; mkdir -p "$w"
    ( cd "$w" && xvlog -sv -L xpm -d RXPH=$(python3 -c "print($ph/1000.0)") -d BP_CLKS=$3 -d HANG_TX=$4 -d HANG_RX=$5 -d BPTO=$6 -d BPRTY=$7 $(for f in $SRCS; do echo ../$f; done) ../gth_wiz_model.sv ../tb_lat_core126.sv "$XILINX_VIVADO/data/verilog/src/glbl.v" > xvlog.log 2>&1 \
      && xelab -L xpm -L unisims_ver -debug off -generic_top "RATE_MATCH=$rm_" -generic_top "RM_OWN=$own" -generic_top "RM_DIRECT=0" -generic_top "GO_REG=$goreg" tb_lat_core126 work.glbl -s s > xelab.log 2>&1 && xsim s -R > xsim.log 2>&1 )
    grep -E "^(ORD|DONE|TIMEOUT|LINK|UP |NOLINK|ID|FEATURES|GTSTAT|SAFETY|GT_BUF|END)" "$w/xsim.log" > "$OUT/$t.log"
    echo "$c $t: $(grep -c ^ORD "$OUT/$t.log") orders; $(grep -E 'DONE|TIMEOUT|LINK|END' "$OUT/$t.log" | tr '\n' ' ')"
  }
  for ph in $PHASES; do run "ord_${rm_}_${own}_${ph}" $ph 100 0 0 4833984 3; done
  if [ $bp = 1 ]; then
    for sc in $SCEN; do case "$sc" in
      normal) ;;   # the phase-0 ord_ run above is the normal scenario
      retry)  run "bypass_retry" 0 100 1 1 3000 2;;
      giveup) run "bypass_giveup" 0 100 99 99 1500 2;;
    esac; done
  fi
  python3 "$ROOT/results/b96e/core_lat.py" "$OUT" "$H/core_sim/$c.json" > "$OUT/reduction.txt"; cat "$OUT/reduction.txt"
done
