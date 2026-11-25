#!/usr/bin/env bash
# Brief 224 arm 2: p4, p5, p6, three runs each, a record after each (no push: the run records are checked against the private-prompt gate first).
# Stops: cumulative real dollars of the arm above 50 (checked before each run), one run above 20 (after it). Ledger: pilots/224/cost_ledger.tsv.
set -uo pipefail
ROOT=/home/brendan/Claude_sandbox/_worktrees/224-long-output; cd "$ROOT"
DESIGNS=(p4_fir_dsp p5_async_fifo p6_glitchfree_mux)
LED=pilots/224/cost_ledger.tsv
[ -f "$LED" ] || printf 'design\trun\trun_id\tagent_sha\treal_usd\ttokens\ttruncated_calls\tstop\n' > "$LED"
for K in 1 2 3; do for ID in "${DESIGNS[@]}"; do
  [ -d pilots/224/$ID/arm2_run$K ] && continue
  TOT=$(awk -F'\t' 'NR>1{s+=$5} END{print s+0}' "$LED")
  if awk -v t="$TOT" 'BEGIN{exit !(t>50)}'; then echo "STOP cumulative real dollars $TOT above 50" | tee pilots/224/STOPPED; exit 9; fi
  BEFORE=$(ls -1 runs | grep '^2026' | sort | tail -1)
  pilots/224/run_agent.sh "$ID" "$K"
  RID=$(ls -1 runs | grep '^2026' | sort | tail -1)
  D=pilots/224/$ID/arm2_run$K; mkdir -p "$D"
  if [ "$RID" = "$BEFORE" ] || [ ! -f runs/$RID/model_calls.jsonl ]; then echo "no run record for $ID run $K ($RID)" > "$D/NO_RECORD.txt"; cp runs/_logs/arm2_${ID}_r${K}.log "$D/agent_stdout.log"; echo "STOP no record: $ID $K" | tee pilots/224/STOPPED; exit 8; fi
  pilots/224/record_one.sh "$ID" "$K" "$RID"
  LAST=$(tail -1 "$LED" | cut -f5)
  if awk -v t="$LAST" 'BEGIN{exit !(t>20)}'; then echo "STOP one run above 20 USD: $ID $K $LAST" | tee pilots/224/STOPPED; exit 7; fi
done; done
echo ALL_DONE > pilots/224/STOPPED
