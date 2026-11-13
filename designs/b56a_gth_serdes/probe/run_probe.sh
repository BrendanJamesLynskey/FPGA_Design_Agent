#!/usr/bin/env bash
# run_probe.sh <name> [<name> ...]: the brief 56A licence and build probe, one Vivado process per IP, from the repo root.
# Take a heavy slot first (_handoff/take_heavy_slot.sh, text with "Vivado impl" and "peak <N>G"). Output: probe_logs/<name>.log and
# the RESULT lines in probe_logs/results.txt. Each run is capped at 8 GB (systemd-run MemoryMax) and nice'd.
set -u
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
VIVADO="${VIVADO:-$(python3 "$ROOT/flow/version_pin.py" --vivado)}"
OUT="${PROBE_OUT:-$ROOT/designs/b56a_gth_serdes/build/probe}"
mkdir -p "$OUT"; cd "$OUT"
for n in "$@"; do
  # /usr/bin/time inside the scope: its "Maximum resident set size" is that of the largest process of the run (wrapper, binary or helper)
  PROBE="$n" PROBE_DIR="$ROOT/designs/b56a_gth_serdes/probe" systemd-run --user --scope -p MemoryMax=8G nice -n 15 \
    /usr/bin/time -v "$VIVADO" -mode batch -nojournal -log "$n.log" -source "$ROOT/designs/b56a_gth_serdes/probe/ip_probe.tcl" > "$n.stdout" 2> "$n.time"
  grep -E '^(PROBE|RESULT)' "$n.log" >> results.txt
  grep -E 'Maximum resident' "$n.time" | sed "s/^/PEAK_RSS $n /" >> results.txt
done
