#!/usr/bin/env bash
# run_quartus_sta.sh: brief 207 analysis-only re-runs on fits run_quartus.sh already made (no refit), each in a heavy slot.
#   run_quartus_sta.sh <out dir> <fit dir name> <variant> ...
# Used for: the D analysis (set_max_skew as an assertion) on the N and U fits, so the routed skew of a fit made WITHOUT the
# skew constraint is measured the same way (E6); and DD on the D fit (E5).
set -u
here="$(cd "$(dirname "$0")" && pwd)"
Q=/home/brendan/altera_lite/25.1std/quartus/bin
H=/home/brendan/Claude_sandbox/_handoff
out="$1"; fit="$2"; shift 2
while :; do
  load=$(cut -d' ' -f1 /proc/loadavg); avail=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)
  if awk -v l="$load" 'BEGIN{exit !(l < 6)}' && [ "$avail" -gt 12 ]; then
    lock=$("$H/take_heavy_slot.sh" "207: Quartus sta $fit, $(date +%H:%M), expected end $(date -d '+3 min' +%H:%M), peak 2G, no Vivado") && break
  fi
  sleep 60
done
w="$out/$fit"
( systemd-run --user --scope -q -p MemoryMax=3G nice -n 15 \
    "$Q/quartus_sta" -t "$here/q_sta.tcl" "$w/proj" "$here/q_variant.sdc" "$w" 6.400 "$@" > "$w.sta_extra.log" 2>&1 ) || echo "FAILED sta $w"
case "$(cat "$lock" 2>/dev/null)" in "207:"*) rm -f "$lock";; esac
echo "$(date +%H:%M) $fit: $* done"
