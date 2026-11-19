#!/usr/bin/env bash
# produce_block.sh: how ext/pcs_unit_p0.dcp was made, as a supplier would: the supplier's RTL (ext/reference/) implemented out of context
# in a pblock on the KR260's part, placed, routed and locked at routing level (lock_design -level routing), written as a checkpoint.
# This runs OUTSIDE the project build (brief 100's ooc.tcl, no agent, no managed project). The project only receives the file and checks it
# (flow/managed_import.py check). Take a heavy slot first (_handoff/take_heavy_slot.sh "<prefix>: ..."); Vivado 2026.1, one thread.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"; ROOT="$HERE/../.."
R="$ROOT/results/102_managed_pr/block"; mkdir -p "$R"
export B100_PART=xck26-sfvc784-2LV-c
B100_SRC="$HERE/ext/reference/b96_pkg.sv $HERE/ext/reference/pcs_tx.sv $HERE/ext/reference/pcs_unit.sv" B100_TOP=pcs_unit \
  B100_PERIOD="${PERIOD:-4.0}" B100_PBLOCK="${PBLOCK:-SLICE_X26Y70:SLICE_X37Y89}" B100_OUT="$R/blk_p0" \
  "$ROOT/designs/b100_rapidwright/scripts/viv.sh" "$ROOT/designs/b100_rapidwright/scripts/ooc.tcl" "$R/blk_p0.log"
# the supplier drops its own clock constraint (neutralise_block.tcl): the integrator's clock reaches the block through its port
FDA_PR_IN="$R/blk_p0_ooc.dcp" FDA_PR_OUT="$HERE/ext/pcs_unit_p0.dcp" "$ROOT/designs/b100_rapidwright/scripts/viv.sh" "$HERE/scripts/neutralise_block.tcl" "$R/neutralise.log"
( cd "$HERE/ext" && { /opt/Xilinx/2026.1/Vivado/bin/vivado -version | head -1; sha256sum reference/*.sv pcs_unit_p0.dcp; } > PRODUCED.txt )
echo "wrote ext/pcs_unit_p0.dcp, ext/PRODUCED.txt"
