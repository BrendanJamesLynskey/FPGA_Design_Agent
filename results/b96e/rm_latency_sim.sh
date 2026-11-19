#!/bin/bash
# Brief 96E: the elastic buffer's latency by implementation (0 = rate_match with AMD's xpm_fifo_async, 1 = rate_match_gp, our gray-pointer buffer), fill target HI and phase, on AMD's real macros in
# xsim 2026.1 (-L xpm), one testbench (designs/b96_kr260_10g/sim/tb_rm_latency.sv). Prints the SUMMARY lines that results/b96e/rm_latency_sim.json holds. Simulation only: needs no heavy slot (load under 6, more than 12 GB free).
# usage: rm_latency_sim.sh "<impl>:<hi>" ...   (default: 0:4 0:1 1:1)      Work directory: $WORK (default <repo>/build/rm_latency96e).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; D=designs/b96_kr260_10g
WORK="${WORK:-$ROOT/build/rm_latency96e}"; mkdir -p "$WORK"; cd "$WORK"
set +u; source /opt/Xilinx/2026.1/Vivado/settings64.sh >/dev/null 2>&1; set -u
PHASES="${PHASES:-0 1550 3100 4650}"
CASES=("$@"); [ ${#CASES[@]} -eq 0 ] && CASES=(0:4 0:1 1:1)
for cs in "${CASES[@]}"; do
  impl="${cs%%:*}"; hi="${cs##*:}"
  for ph in $PHASES; do
    t="${impl}_${hi}_${ph}"
    sed -e "s/PH_PS = 0/PH_PS = $ph/" -e "s/IMPL = 0/IMPL = $impl/" -e "s/HI = 4/HI = $hi/" "$ROOT/$D/sim/tb_rm_latency.sv" > tb_$t.sv
    xvlog -sv -L xpm "$ROOT/$D/rtl/rate_match.sv" "$ROOT/$D/rtl/rate_match_gp.sv" tb_$t.sv "$XILINX_VIVADO/data/verilog/src/glbl.v" > xvlog_$t.log 2>&1 \
      && xelab -L xpm -L unisims_ver -debug off tb_rm_latency work.glbl -s x$t > xelab_$t.log 2>&1 && xsim x$t -R > xsim_$t.log 2>&1
    grep SUMMARY xsim_$t.log | sed "s/^/impl $impl hi $hi  /"
    grep -q SUMMARY xsim_$t.log || { echo "impl $impl hi $hi phase $ph: NO SUMMARY (see $WORK/xvlog_$t.log xelab_$t.log xsim_$t.log)"; }
  done
done
