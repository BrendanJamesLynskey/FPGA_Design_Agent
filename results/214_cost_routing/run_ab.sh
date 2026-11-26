#!/usr/bin/env bash
# Brief 214 A/B driver: the runs of order.tsv in order, one at a time. A run with no slot yet is retried; a usage or CLI stop ends the series (STOP flag in _scratch_214).
set -uo pipefail
ROOT=/home/brendan/Claude_sandbox/_worktrees/214-cost-routing
cd "$ROOT"
grep -v '^#' results/214_cost_routing/order.tsv | while IFS=$'\t' read -r N ID K ARM; do
  D="results/214_cost_routing/runs/${N}_${ID}_k${K}_${ARM}"
  [ -f "$D/RUN_ID.txt" ] && continue
  while :; do
    results/214_cost_routing/run_one.sh "$N" "$ID" "$K" "$ARM"; rc=$?
    [ $rc -eq 6 ] && { sleep 120; continue; }
    break
  done
  [ $rc -ge 3 ] && [ $rc -ne 9 ] && { echo "series stopped at $N with $rc"; exit $rc; }
done
echo SERIES_DONE
