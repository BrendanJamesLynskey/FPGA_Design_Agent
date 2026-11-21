#!/usr/bin/env bash
# Brief 127: re-run only the in-context timing report (results/b127/ctx_timing.tcl) on an existing post-route checkpoint of build rm_gp_itch, under a heavy slot.
#   results/b127/ctx_only.sh [wait minutes, default 120]
set -uo pipefail
WAIT="${1:-120}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; H=/home/brendan/Claude_sandbox/_handoff
cd "$ROOT"
TEXT="127: Vivado ctx timing, no implementation, peak 3G, $(date +%H:%M), expected end +10 min"
n=0
while true; do
  out="$("$H/take_heavy_slot.sh" --env "$TEXT" 2>/dev/null)" && [ -n "$out" ] && { eval "$out"; break; }
  n=$((n+1)); [ "$n" -ge "$WAIT" ] && { echo "no heavy slot within $WAIT minutes"; exit 1; }
  read -r -t 60 < <(tail -f /dev/null) || true
done
release() { case "$(cat "$HEAVY_LOCK" 2>/dev/null)" in "127:"*) rm -f "$HEAVY_LOCK";; esac; }
trap release EXIT
B=designs/b96_kr260_10g/rm_gp_itch/build/base; OUT=results/b127/builds/rm_gp_itch
VIVADO="$(python3 flow/version_pin.py --vivado)"
systemd-run --user --scope -p MemoryMax=6G nice -n 15 "$VIVADO" -mode batch -nojournal -nolog -source results/b127/ctx_timing.tcl -tclargs "$B/post_route.dcp" "$OUT" > "$OUT/ctx_timing.log" 2>&1
echo "done: $OUT/ctx_timing.txt"
