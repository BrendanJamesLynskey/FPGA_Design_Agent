#!/usr/bin/env bash
# Brief 209: all runs in order (p1, p2-p4, p5, p6; 3 runs each), a record and a push after each, stopping on the cost rules.
# Usage: run_all.sh [first_design_index] ; ledger: pilots/209/cost_ledger.tsv (real dollars from each summary.json cost_usd)
set -uo pipefail
ROOT=/home/brendan/Claude_sandbox/_worktrees/209-kr260-pilot; cd "$ROOT"
DESIGNS=(p1_clkmeter p2_bram_rom p3_crc_engine p4_fir_dsp p5_async_fifo p6_glitchfree_mux)
LED=pilots/209/cost_ledger.tsv
[ -f "$LED" ] || printf 'design\trun\trun_id\tagent_sha\treal_usd\ttokens\ttruncated_calls\tstop\n' > "$LED"
for ID in "${DESIGNS[@]}"; do for K in 1 2 3; do
  [ -d pilots/209/$ID/run$K ] && continue
  TOT=$(awk -F'\t' 'NR>1{s+=$5} END{print s+0}' "$LED")
  if awk -v t="$TOT" 'BEGIN{exit !(t>130)}'; then echo "STOP cumulative real dollars $TOT above 130" | tee pilots/209/STOPPED; exit 9; fi
  BEFORE=$(ls -1 runs | grep '^2026' | sort | tail -1)
  rm -f runs/_logs/${ID}_r${K}.log
  pilots/209/run_agent.sh "$ID" "$K"
  RID=$(ls -1 runs | grep '^2026' | sort | tail -1)
  D=pilots/209/$ID/run$K; mkdir -p "$D"
  if [ "$RID" = "$BEFORE" ] || [ ! -f runs/$RID/model_calls.jsonl ]; then echo "no run record for $ID run $K ($RID)" > "$D/NO_RECORD.txt"; cp runs/_logs/${ID}_r${K}.log "$D/agent_stdout.log"; git add -A pilots; git commit -qm "209: $ID run $K without record" ; git push -q; echo "STOP no record: $ID $K" | tee pilots/209/STOPPED; exit 8; fi
  pilots/209/record_one.sh "$ID" "$K" "$RID"
  LAST=$(tail -1 "$LED" | cut -f5)
  git add -A pilots; git commit -qm "209: $ID run $K record ($RID)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01SHVDMMSkFUpQfjmfYnAbny"; git push -q
  if awk -v t="$LAST" 'BEGIN{exit !(t>20)}'; then echo "STOP one run above 20 USD: $ID $K $LAST" | tee pilots/209/STOPPED; exit 7; fi
done; done
echo ALL_DONE > pilots/209/STOPPED
