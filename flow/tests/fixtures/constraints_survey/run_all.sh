#!/usr/bin/env bash
# The brief 105 measurements (M1-M3), one out-of-context Vivado run per variant: run_all.sh <out dir> [variant ...]
# Needs the heavy slot (_handoff/take_heavy_slot.sh "105: ..."); the caller holds it and sets FDA_VIVADO_THREADS=1.
# Variants: m1_a7_attr m1_a7_plain m1_k26_attr m1_k26_plain m2_0 m2_1 m2_2 m2_3 m3_a m3_b m3_c m3_d
set -u
here="$(cd "$(dirname "$0")" && pwd)"
flow="$(cd "$here/../../.." && pwd)"
V="${VIVADO:-$(python3 "$flow/version_pin.py" --vivado)}"
A7=xc7a100tcsg324-1; K26=xck26-sfvc784-2LV-c
out="$1"; shift; mkdir -p "$out"
names=("$@")
[ ${#names[@]} -eq 0 ] && names=(m1_a7_attr m1_a7_plain m1_k26_attr m1_k26_plain m2_0 m2_1 m2_2 m2_3 m3_a m3_b m3_c m3_d)
for n in "${names[@]}"; do
  case "$n" in
    m1_a7_attr)    args="m1 m1_sync m1_sync $A7 AREG=1" ;;
    m1_a7_plain)   args="m1 m1_sync m1_sync $A7 AREG=0" ;;
    m1_k26_attr)   args="m1 m1_sync m1_sync $K26 AREG=1" ;;
    m1_k26_plain)  args="m1 m1_sync m1_sync $K26 AREG=0" ;;
    m2_*)          args="m2 m2_fanout m2_fanout $A7 MODE=${n#m2_}" ;;
    m3_a|m3_b|m3_c|m3_d) args="m3 m3_bus $n $A7 W=16" ;;
    *) echo "unknown variant $n"; continue ;;
  esac
  set -- $args
  systemd-run --user --scope -q -p MemoryMax=6G nice -n 15 \
    "$V" -mode batch -nojournal -nolog -source "$here/measure.tcl" \
    -tclargs "$flow" "$here" "$1" "$2" "$3" "$4" "$5" "$out/$n" > "$out/$n.log" 2>&1 || echo "FAILED $n"
done
