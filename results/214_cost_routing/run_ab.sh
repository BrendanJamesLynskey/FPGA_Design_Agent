#!/usr/bin/env bash
# Brief 214 A/B driver: the runs of order.tsv in order. Usage: run_ab.sh [W T]: worker W of T takes the runs with n mod T = W (default one worker, all runs). A run with no slot yet is retried; a usage or CLI stop ends the series (STOP flag in _scratch_214).
set -uo pipefail
ROOT=/home/brendan/Claude_sandbox/_worktrees/214-cost-routing
W="${1:-0}"; T="${2:-1}"
cd "$ROOT"
grep -v '^#' results/214_cost_routing/order.tsv | while IFS=$'\t' read -r N ID K ARM; do
  [ $((N % T)) -ne "$W" ] && continue
  D="results/214_cost_routing/runs/${N}_${ID}_k${K}_${ARM}"
  [ -f "$D/RUN_ID.txt" ] && continue
  while :; do
    results/214_cost_routing/run_one.sh "$N" "$ID" "$K" "$ARM"; rc=$?
    [ $rc -eq 6 ] && { sleep 120; continue; }
    break
  done
  [ $rc -ne 0 ] && { echo "series stopped at $N with $rc"; exit $rc; }
done
echo SERIES_DONE
