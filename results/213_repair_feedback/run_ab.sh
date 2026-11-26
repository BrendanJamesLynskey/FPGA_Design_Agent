#!/usr/bin/env bash
# Brief 213 A/B driver: the 18 runs of order.tsv, one at a time. A run with no slot yet is retried; usage or CLI stops end the series (flag file STOP in the scratch folder).
set -uo pipefail
ROOT=/home/brendan/Claude_sandbox/_worktrees/213-repair-feedback; S=/home/brendan/Claude_sandbox/_scratch_213
cd "$ROOT"
grep -v '^#' results/213_repair_feedback/order.tsv | while IFS=$'\t' read -r N ID K ARM; do
  D="results/213_repair_feedback/runs/${N}_${ID}_k${K}_${ARM}"
  [ -f "$D/RUN_ID.txt" ] && continue
  while :; do
    results/213_repair_feedback/run_one.sh "$N" "$ID" "$K" "$ARM"; rc=$?
    [ $rc -eq 6 ] && { sleep 120; continue; }
    break
  done
  [ $rc -ge 3 ] && [ $rc -ne 9 ] && { echo "series stopped at $N with $rc"; exit $rc; }
done
echo SERIES_DONE
