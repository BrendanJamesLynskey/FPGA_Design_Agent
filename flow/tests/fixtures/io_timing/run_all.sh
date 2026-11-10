#!/usr/bin/env bash
# Vivado 2025.2 runs of the I/O-timing fixtures (brief 20 part B): one Vivado per group (synthesis, place and route, then
# every variant re-timed on the routed netlist). run_all.sh <out dir> [group ...]
# Needs a heavy slot with "Vivado impl" in the text (_handoff/take_heavy_slot.sh); the caller holds it.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
flow="$(cd "$here/../../.." && pwd)"
out="$1"; shift; mkdir -p "$out"
declare -A G=(
  [adc]="io_adc|-|io_i1 io_i2 io_i3 io_i3b io_i8 io_i9 io_i10 io_v6"
  [dac]="io_dac|-|io_i4 io_i4b io_v1 io_v3 io_v4 io_v5"
  [fwd]="io_fwd|-|io_i7 io_i7c io_i7b"
  [ddr]="io_ddr|-|io_i5 io_i5b"
  [edge]="io_edge|USE_IDELAY=0|io_i6"
  [edgedly]="io_edge|USE_IDELAY=1 TAPS=${FDA_IO_TAPS:-16}|io_i6b"
  [mmcm]="io_mmcm|-|io_v2 io_v2a"
)
groups=("$@"); [ ${#groups[@]} -eq 0 ] && groups=(adc dac fwd ddr edge edgedly mmcm)
for g in "${groups[@]}"; do
  IFS='|' read -r top gen vars <<< "${G[$g]}"
  [ "$gen" = "-" ] && gen=""
  ( cd "$out" && systemd-run --user --scope -q --unit="fda-b20b-io-$g-$$" -p MemoryMax=6G nice -n 15 \
    /opt/Xilinx/2025.2/Vivado/bin/vivado -mode batch -nojournal -log "$out/$g.log" -source "$here/measure_io.tcl" \
    -tclargs "$flow" "$here" "$top" "$out/$g" "$gen" $vars > /dev/null 2>&1 ) || echo "FAILED $g"
  echo "done $g $(date +%H:%M:%S)"
done
