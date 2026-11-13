#!/usr/bin/env bash
# run_xsim.sh: the GT Wizard loopback simulation (xsim, Vivado 2026.1) from the repo root. Writes <work>/sim.log and prints the CHECK and
# RESULT lines. Simulation-only, but it starts Vivado: take a heavy slot ("Vivado", peak 8G) first. Capped at 8 GB.
set -eu
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
VIVADO="${VIVADO:-$(python3 "$ROOT/flow/version_pin.py" --vivado)}"
WORK="${1:-$ROOT/designs/b56a_gth_serdes/build/xsim}"
mkdir -p "$WORK"; cd "$WORK"
systemd-run --user --scope -p MemoryMax=8G nice -n 15 \
  /usr/bin/time -v "$VIVADO" -mode batch -nojournal -log vivado.log -source "$ROOT/designs/b56a_gth_serdes/sim/run_xsim.tcl" -tclargs "$WORK" > stdout.txt 2> time.txt
grep -E '^(CHECK|RESULT|TB-DONE|XSIM-DONE)' stdout.txt vivado.log "$WORK"/proj/sim.sim/sim_1/behav/xsim/simulate.log 2>/dev/null | sort -u | tee sim_summary.txt || true
grep -E 'Maximum resident' time.txt || true
