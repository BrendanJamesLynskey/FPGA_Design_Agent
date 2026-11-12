#!/usr/bin/env bash
# repro.sh: the reproducibility builds, one at a time (run it where nothing else is building).
#
#   results/54_reproducible/repro.sh <jobs file> <raw dir>
#
# Each line of the jobs file: <label> <tree> <design dir relative to the tree> <threads> [VAR=value ...]
# <tree> is a clean checkout of the same commit (a different directory per tree). Each job runs that tree's own
# flow/run_vivado.sh <design> base with FDA_VIVADO_THREADS, FDA_BUILD_CACHE=0 (always a fresh build), FDA_RESULT_HASH=1
# (placement and routing hashes, flow/result_hash.py) and MEM_MAX=6G, then copies the build's records, the routed
# reports and the bitstream into <raw dir>/<label>/. Lines starting with # are skipped.
set -uo pipefail
JOBS="$1"
RAW="$2"
mkdir -p "$RAW"
while read -r label tree design threads extra; do
  case "$label" in ''|'#'*) continue ;; esac
  dst="$RAW/$label"
  rm -rf "$dst"
  mkdir -p "$dst"
  echo "repro: $label ($tree/$design, $threads threads, ${extra:-no extras}) at $(date +%H:%M:%S)"
  rm -rf "$tree/$design/build/base" "$tree/$design/build/base.prev"
  # shellcheck disable=SC2086
  env FDA_VIVADO_THREADS="$threads" FDA_BUILD_CACHE=0 FDA_RESULT_HASH=1 MEM_MAX=6G $extra \
      bash "$tree/flow/run_vivado.sh" "$tree/$design" base >"$dst/runner.txt" 2>&1
  rc=$?
  echo "$rc" >"$dst/rc.txt"
  out="$tree/$design/build/base"
  for f in manifest.json run.json gates.json stages.txt result_hash.json tool.txt timing_summary.rpt utilization.rpt \
           power.rpt drc.rpt methodology.rpt cdc.rpt check_timing.rpt inputs.tcl; do
    cp "$out/$f" "$dst/" 2>/dev/null || true
  done
  cp "$out"/*.bit "$dst/" 2>/dev/null || true
  echo "repro: $label exit $rc at $(date +%H:%M:%S)"
done <"$JOBS"
