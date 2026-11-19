#!/usr/bin/env bash
# run_e2_a7.sh: the second device family for experiment 2: reloc_top (four pcs_unit copies, no pblocks) on the Nexys A7's xc7a100t, placed by Vivado
# alone (this run is also one more Vivado full-build timing), then experiment 2's router comparison at two periods. Needs the heavy slot.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$HERE/../../.."; W="${W:-/home/brendan/Claude_sandbox/_worktrees/100b-work}"
RTL="$ROOT/designs/b100_rapidwright/rtl"; B96="$ROOT/designs/b96_kr260_10g/rtl"
mkdir -p "$W/a7base"
[ -f "$W/a7base/a7_placed.dcp" ] || B100_THREADS=1 B100_PART=xc7a100tcsg324-1 B100_TOP=reloc_top B100_PERIOD=6.0 B100_SRC="$RTL/reloc_top.sv $B96/b96_pkg.sv $B96/pcs_tx.sv $RTL/pcs_unit.sv" \
  B100_OUT="$W/a7base/a7" "$HERE/meas.sh" a7_full "$W/a7base" vivado "$ROOT/designs/b100_rapidwright/scripts/impl.tcl"
"$HERE/run_e2.sh" a7 "$W/a7base/a7_placed.dcp" 4.5 6.0
