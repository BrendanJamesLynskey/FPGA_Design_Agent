#!/usr/bin/env bash
# run_all.sh: every variant in variants.txt through measure.tcl (Vivado from flow/version_pin.py, goldens made on 2025.2, out-of-context, one at a time).
#   flow/tests/fixtures/fsm_discipline/run_all.sh <out dir> <impl 0|1> [variant ...]
# Needs a heavy slot (the caller's) and sets a unique systemd scope per run (memory cap 6 GB).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:?out dir}"; IMPL="${2:-0}"; shift 2
V="${VIVADO:-$(python3 "$HERE/../../../version_pin.py" --vivado)}"
PERIOD="${FSM_PERIOD:-2.5}"
mkdir -p "$OUT"
while IFS='|' read -r name top gen ext mc; do
  case "$name" in \#*|"") continue;; esac
  if [ "$#" -gt 0 ]; then case " $* " in *" $name "*) ;; *) continue;; esac; fi
  [ -s "$OUT/$name.kv" ] && [ "$IMPL" = 0 ] && [ -z "${FSM_FORCE:-}" ] && continue
  echo "== $name $(date +%T)"
  systemd-run --user --scope -q --unit="fda-b24-$name-$$" -p MemoryMax=6G nice -n 15 \
    "$V" -mode batch -log "$OUT/$name.log" -journal "$OUT/$name.jou" -nojournal \
    -source "$HERE/measure.tcl" -tclargs "$name" "$top" "$gen" "$PERIOD" "$ext" "$IMPL" "$OUT" "$mc" > "$OUT/$name.stdout" 2>&1 || echo "FAILED $name"
done < "$HERE/variants.txt"
