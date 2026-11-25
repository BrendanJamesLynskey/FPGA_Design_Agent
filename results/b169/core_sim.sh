#!/bin/bash
# Brief 169: the whole core in xsim 2026.1 with AMD's real XPM macros (as results/b126/core_sim.sh), for the prototype cuts of designs/b96_kr260_10g/lat_cuts169 behind their parameters.
#   Cases (name: EARLY_MAC FAST_PRE):  base 0 0 (the parameters off: must equal brief 126's lat_all3_bypass), early 1 0, fast 0 1, both 1 1.
#   Files: base rtl/ then lat_all3/rtl then rm_gp_bypass/rtl then lat_cuts169/rtl (later directories replace earlier files of the same name), the same order as the build's source list.
#   Phases: the receive clock lags the transmit clock by 0, 1550, 3100, 4650 ps. Bypass start-up scenario `retry` (one hung alignment per side, as results/b126) with SCEN="normal retry".
#   usage: results/b169/core_sim.sh [cases, default "base early fast both"]      Output: results/b169/core_sim/<case>/ord_<phase>.log and <case>.json (reduce169.py).
#   Simulation only: no heavy slot needed while load is under 6 and more than 12 GB is free. The stand-in transceiver has NO elastic buffers (the bypass's saving cannot appear).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; D=designs/b96_kr260_10g; R=$ROOT/$D/rtl; B=$ROOT/$D/rm_gp_bypass/rtl; V=$ROOT/$D/lat_all3/rtl; C=$ROOT/$D/lat_cuts169/rtl; H=$ROOT/results/b169; H6=$ROOT/results/b126
WORK="${WORK:-$ROOT/build/core_sim169}"; mkdir -p "$WORK" "$H/${OUTD:-core_sim}"; cd "$WORK"
set +u; source /opt/Xilinx/2026.1/Vivado/settings64.sh >/dev/null 2>&1; set -u
CASES="${*:-base early fast both}"; PHASES="${PHASES:-0 1550 3100 4650}"; SCEN="${SCEN:-normal}"; NORD="${NORD:-8}"
conv() { sed -e 's/always_ff @(/always @(/' -e 's/INIT_SYNC_FF(0)/INIT_SYNC_FF(1)/' "$1" > "$2/$(basename "$1")"; }
python3 "$H6/make_bp_model.py" "$ROOT/$D/sim/gth_wiz_model96e.sv" "$WORK/gth_wiz_model126bp.sv"
SRCS="b96_pkg.sv pcs_tx.sv pcs_rx.sv mac64_tx.sv mac64_rx.sv hs_vec.sv frame_src.sv trade64.sv rate_match.sv rate_match_gp.sv tx_path.sv rx_path.sv rx_path_legacy.sv gt_bp_gate.sv gt_bp_ctl.sv b96_core.sv"
for c in $CASES; do
  case "$c" in
    base)  e=0; f=0;; early) e=1; f=0;; fast) e=0; f=1;; both) e=1; f=1;;
    *) echo "unknown case $c"; continue;;
  esac
  X="$WORK/x_$c"; rm -rf "$X"; mkdir -p "$X"; for d in $R $V $B $C; do for fl in "$d"/*.sv; do conv "$fl" "$X"; done; done
  python3 "$H/make_tb169.py" "$ROOT/$D/sim/tb_lat_core.sv" "$X/tb_lat_core169.sv"
  sed 's/parameter int NORD = 8/parameter int NORD = '"$NORD"'/' -i "$X/tb_lat_core169.sv"
  cp gth_wiz_model126bp.sv "$X/gth_wiz_model.sv"
  OUT="$H/${OUTD:-core_sim}/$c"; mkdir -p "$OUT"
  run() {   # name, phase ps, BP_CLKS, hang tx, hang rx, timeout, retries
    local t="$1" ph="$2" w="$X/r_$1"; mkdir -p "$w"
    ( cd "$w" && xvlog -sv -L xpm -d RXPH=$(python3 -c "print($ph/1000.0)") -d BP_CLKS=$3 -d HANG_TX=$4 -d HANG_RX=$5 -d BPTO=$6 -d BPRTY=$7 $(for fl in $SRCS; do echo ../$fl; done) ../gth_wiz_model.sv ../tb_lat_core169.sv "$XILINX_VIVADO/data/verilog/src/glbl.v" > xvlog.log 2>&1 \
      && xelab -L xpm -L unisims_ver -debug off -generic_top "RATE_MATCH=0" -generic_top "RM_OWN=0" -generic_top "RM_DIRECT=0" -generic_top "GO_REG=0" -generic_top "EARLY_MAC=$e" -generic_top "FAST_PRE=$f" tb_lat_core126 work.glbl -s s > xelab.log 2>&1 && xsim s -R > xsim.log 2>&1 )
    grep -E "^(ORD|RET|DONE|TIMEOUT|LINK|UP |NOLINK|ID|FEATURES|GTSTAT|SAFETY|GT_BUF|END)|EARLY MISMATCH" "$w/xsim.log" > "$OUT/$t.log"
    echo "$c $t: $(grep -c ^ORD "$OUT/$t.log") orders, $(grep -c ^RET "$OUT/$t.log") returned; $(grep -E 'DONE|TIMEOUT|LINK|END' "$OUT/$t.log" | tr '\n' ' ') mismatches $(grep -c MISMATCH "$OUT/$t.log")"
  }
  for ph in $PHASES; do run "ord_${ph}" $ph 100 0 0 4833984 3; done
  for sc in $SCEN; do case "$sc" in
    normal) ;;
    retry)  run "bypass_retry" 0 100 1 1 3000 2;;
  esac; done
  python3 "$H/reduce169.py" "$OUT" "$H/${OUTD:-core_sim}/$c.json" > "$OUT/reduction.txt"; cat "$OUT/reduction.txt"
done
