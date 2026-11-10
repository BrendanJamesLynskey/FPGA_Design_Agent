#!/usr/bin/env bash
# Vivado 2025.2 runs of the timing-exception fixtures (brief 20), one Vivado per fixture:
#   run_all.sh <out dir> [fixture ...]          (FDA_TEX_IMPL="tex_e1 tex_e10" also places and routes those)
# Needs a heavy slot (_handoff/take_heavy_slot.sh, "Vivado impl" in the text when FDA_TEX_IMPL is set); the caller holds it.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
flow="$(cd "$here/../../.." && pwd)"
out="$1"; shift; mkdir -p "$out"
names=("$@")
[ ${#names[@]} -eq 0 ] && names=($(cd "$here/rtl" && ls *.sv | sed 's/\.sv$//'))
for n in "${names[@]}"; do
  impl=0; case " ${FDA_TEX_IMPL:-} " in *" $n "*) impl=1;; esac
  ( cd "$out" && systemd-run --user --scope -q -p MemoryMax=6G nice -n 15 \
    /opt/Xilinx/2025.2/Vivado/bin/vivado -mode batch -nojournal -log "$out/$n.log" -source "$here/measure.tcl" \
    -tclargs "$flow" "$here" "$n" "$out/$n" "$impl" > /dev/null 2>&1 ) || echo "FAILED $n"
done
