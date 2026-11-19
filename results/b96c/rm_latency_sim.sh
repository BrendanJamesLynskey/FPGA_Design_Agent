#!/bin/bash
# Brief 96C addendum 2: rate_match's latency on the Icarus stand-in and on AMD's xpm_fifo_async (xsim 2026.1), four phases, one testbench (sim/tb_rm_latency.sv).
# Prints the SUMMARY lines that results/b96c/rm_latency_sim.json holds. Simulation only (no Vivado build): small, needs no heavy slot (load under 6, more than 12 GB free).
# Work directory: $WORK (default <repo>/build/rm_latency, git-ignored).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; D=designs/b96_kr260_10g
WORK="${WORK:-$ROOT/build/rm_latency}"; mkdir -p "$WORK"; cd "$WORK"
set +u; source /opt/Xilinx/2026.1/Vivado/settings64.sh >/dev/null 2>&1; set -u
# xsim refuses `initial` blocks that also drive always_ff variables (Vivado synthesis and Icarus accept them): a copy without them; the reset initialises the same registers
python3 - "$ROOT/$D/rtl/rate_match.sv" > rm_x.sv <<'PY'
import re, sys
s = open(sys.argv[1]).read()
s = re.sub(r"    initial begin n_ovf = .*?end\n", "", s)
s = re.sub(r"    initial begin\n.*?\n    end\n", "", s, flags=re.S)
print(s)
PY
for ph in 0 1550 3100 4650; do
  sed "s/PH_PS = 0/PH_PS = $ph/" "$ROOT/$D/sim/tb_rm_latency.sv" > tb_$ph.sv
  iverilog -g2012 -s tb_rm_latency -o ic_$ph.vvp "$ROOT/flow/cdc_models/cdc_inj_pkg.sv" "$ROOT/flow/cdc_models/xpm_cdc_models.sv" "$ROOT/$D/rtl/rate_match.sv" tb_$ph.sv && vvp ic_$ph.vvp | grep SUMMARY | sed 's/^/icarus  /'
  xvlog -sv rm_x.sv tb_$ph.sv "$XILINX_VIVADO/data/verilog/src/glbl.v" > xvlog_$ph.log 2>&1 && xelab -L xpm -L unisims_ver -debug off tb_rm_latency work.glbl -s x$ph > xelab_$ph.log 2>&1 && xsim x$ph -R > xsim_$ph.log 2>&1
  grep SUMMARY xsim_$ph.log | sed 's/^/xsim    /'
done
