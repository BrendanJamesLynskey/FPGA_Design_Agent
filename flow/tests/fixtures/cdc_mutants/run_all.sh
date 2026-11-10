#!/usr/bin/env bash
# Synthesis-only run of the CDC fixtures (one Vivado per fixture, about 1 min each): run_all.sh <out dir> [fixture ...]
# Needs the heavy slot (_handoff/take_heavy_slot.sh); the caller holds it. Writes <out>/<fixture>/cdc_synth.rpt and cdc_paths_synth.rpt.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
flow="$(cd "$here/../../.." && pwd)"
out="$1"; shift; mkdir -p "$out"
names=("$@")
[ ${#names[@]} -eq 0 ] && names=($(cd "$here/rtl" && ls *.sv | sed 's/\.sv$//'))
for n in "${names[@]}"; do
  systemd-run --user --scope -q -p MemoryMax=6G nice -n 15 \
    /opt/Xilinx/2025.2/Vivado/bin/vivado -mode batch -nojournal -nolog -source "$here/synth_fixture.tcl" \
    -tclargs "$flow" "$here" "$n" "$out/$n" > "$out/$n.log" 2>&1 || echo "FAILED $n"
done
