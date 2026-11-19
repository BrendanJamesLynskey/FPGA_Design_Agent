#!/bin/bash
# Brief 96E: the whole core's tick-to-trade in xsim 2026.1 with AMD's real XPM macros (sim/tb_lat_core.sv + sim/gth_wiz_model96e.sv), per receive path and per phase between the receive and
# transmit user clocks. usage: core_lat_sim.sh "<rate_match>:<rm_own>" ...   (default: 0:0 1:0 1:1)   PHASES="0 1550 3100 4650" (ps the receive clock lags the transmit clock)
# Writes $WORK/ord_<rm>_<own>_<ph>.log (the ORD lines) and prints a one-line summary per run. Simulation only: no heavy slot needed while load is under 6 and more than 12 GB is free.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; D=designs/b96_kr260_10g; R=$ROOT/$D/rtl
WORK="${WORK:-$ROOT/build/core_lat96e}"; mkdir -p "$WORK"; cd "$WORK"
set +u; source /opt/Xilinx/2026.1/Vivado/settings64.sh >/dev/null 2>&1; set -u
PHASES="${PHASES:-0 1550 3100 4650}"
CASES=("$@"); [ ${#CASES[@]} -eq 0 ] && CASES=(0:0 1:0 1:1)
# xsim refuses a variable driven by an `initial` block and an always_ff (the rtl has several: Vivado synthesis and Icarus accept them): the rtl is compiled from a copy with always_ff turned into
# plain `always` (same behaviour: every one of them is a clocked block) and INIT_SYNC_FF 0 -> 1 (UG974: only the simulation initial value of the synchroniser flops; with 0 the real macros start X and the
# toggling handshakes never settle in xsim). The rtl files themselves are not touched by this.
mkdir -p rtl_x; for f in "$R"/*.sv; do sed -e 's/always_ff @(/always @(/' -e 's/INIT_SYNC_FF(0)/INIT_SYNC_FF(1)/' "$f" > rtl_x/$(basename "$f"); done; R="$WORK/rtl_x"; sed 's/always_ff @(/always @(/' "$ROOT/$D/sim/gth_wiz_model96e.sv" > rtl_x/gth_wiz_model96e.sv; sed 's/always_ff @(/always @(/' "$ROOT/$D/sim/tb_lat_core.sv" > rtl_x/tb_lat_core.sv
SRCS="$R/b96_pkg.sv $R/pcs_tx.sv $R/pcs_rx.sv $R/mac64_tx.sv $R/mac64_rx.sv $R/hs_vec.sv $R/frame_src.sv $R/trade64.sv $R/rate_match.sv $R/rate_match_gp.sv $R/tx_path.sv $R/rx_path.sv $R/rx_path_legacy.sv $R/b96_core.sv"
for cs in "${CASES[@]}"; do
  rm_="${cs%%:*}"; own="${cs##*:}"
  for ph in $PHASES; do
    t="${rm_}_${own}_${ph}"; ns=$(python3 -c "print($ph/1000.0)")
    mkdir -p "x$t"; ( cd "x$t" && xvlog -sv -L xpm -d RXPH=$ns $SRCS $R/gth_wiz_model96e.sv $R/tb_lat_core.sv "$XILINX_VIVADO/data/verilog/src/glbl.v" > xvlog.log 2>&1 \
      && xelab -L xpm -L unisims_ver -debug off -generic_top "RATE_MATCH=$rm_" -generic_top "RM_OWN=$own" tb_lat_core work.glbl -s s > xelab.log 2>&1 && xsim s -R > xsim.log 2>&1 )
    grep -E "^(ORD|DONE|TIMEOUT|LINK)" "x$t/xsim.log" > "ord_$t.log"
    echo "rate_match $rm_ rm_own $own phase_ps $ph: $(grep -c ^ORD ord_$t.log) orders; $(grep -E 'DONE|TIMEOUT|LINK' ord_$t.log | tr '\n' ' ')"
  done
done
