#!/usr/bin/env bash
# run_variants.sh (brief 129): measure_rmii.tcl once per variant, one Vivado at a time, under a heavy slot.
#   run_variants.sh <repo root> <out base dir> <variant[:directive]> ...     (variant k26: the K26 probe, k26/measure_k26.tcl)
# Waits (polling take_heavy_slot.sh) until a slot is free; releases only its own lock ("129:" text).
set -u
root="$1"; base="$2"; shift 2
D=/home/brendan/Claude_sandbox/_handoff
V="$(python3 "$root/flow/version_pin.py" --vivado)"
text="129: Vivado impl b63d RMII IOB variants ($*), $(date +%H:%M), expected end $(date -d '+3 hours' +%H:%M), peak 4G"
lock=""
while [ -z "$lock" ]; do
  lock="$("$D/take_heavy_slot.sh" "$text" 2>/dev/null)" || { lock=""; sleep 0.4; }
done
echo "slot $lock taken $(date +%H:%M:%S)"
release() { case "$(cat "$lock" 2>/dev/null)" in "129:"*) rm -f "$lock";; esac; }
trap release EXIT
mkdir -p "$base"
for v in "$@"; do
  name="${v%%:*}"; dir=""; [ "$v" != "$name" ] && dir="${v#*:}"
  out="$base/$name${dir:+_$dir}"; mkdir -p "$out"
  t0=$(date +%s)
  tcl="$root/results/129_iob_packing/measure_rmii.tcl"; args=("$root" "$out" "$name" "$dir")
  if [ "$name" = k26 ]; then tcl="$root/results/129_iob_packing/k26/measure_k26.tcl"; args=("$root" "$out"); fi
  ( cd "$out" && systemd-run --user --scope -q -p MemoryMax=6G nice -n 15 \
      "$V" -mode batch -nojournal -log "$out/vivado.log" -source "$tcl" \
      -tclargs "${args[@]}" > "$out/stdout.txt" 2>&1 ) || echo "FAILED $v"
  echo "done $v $(( $(date +%s) - t0 )) s $(date +%H:%M:%S)"
done
