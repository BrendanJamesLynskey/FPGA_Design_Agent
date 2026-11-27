#!/usr/bin/env bash
# Brief 217: ONE demonstration run of the R4 arm (not scored). Usage: run_live.sh <design>   (a design folder under results/213_repair_feedback/designs)
# Preflight (pinned CLI, weekly usage), a heavy slot (stage 2 runs a Vivado synthesis), a memory-capped scope, the run's records copied afterwards.
set -uo pipefail
ID="${1:?design}"
ROOT=/home/brendan/Claude_sandbox/_worktrees/217-repair-memory
H=/home/brendan/Claude_sandbox/_handoff; S=/home/brendan/Claude_sandbox/_scratch_213
PY=/home/brendan/Claude_sandbox/FPGA_Design_Agent/.venv/bin/python
cd "$ROOT"; mkdir -p runs/_logs
LOG="runs/_logs/217_live_${ID}.log"
ver=$("$S/bin/claude" --version | cut -d' ' -f1)
[ "$ver" = 2.1.321 ] && [ "$(sha256sum "$S/bin/claude" | cut -d' ' -f1)" = "$(cat "$S/bin/claude.sha256")" ] || { echo "PREFLIGHT_FAIL: CLI $ver" | tee -a "$LOG"; exit 4; }
pct=$("$H/usage_check.sh" 2>&1 | grep 'Current week (all models)' | grep -o '[0-9]*% used' | head -1 | tr -d '%used ')
echo "$(date '+%F %T') live run $ID weekly_before=${pct}%" | tee -a "$LOG"
[ "${pct:-100}" -ge 90 ] && { echo "weekly usage >= 90: stop (BLOCKED)" | tee -a "$LOG"; exit 5; }
TEXT="217: live R4 demonstration $ID, stage 2 (Vivado synth), $(date +%H:%M), expected end +60min, peak 4G"
if ! eval "$("$H/take_heavy_slot.sh" --env "$TEXT")" 2>/dev/null || [ -z "${HEAVY_LOCK:-}" ]; then echo "no slot yet" | tee -a "$LOG"; exit 6; fi
echo "$(date '+%F %T') slot $HEAVY_LOCK" >> "$LOG"
trap 'case "$(cat "$HEAVY_LOCK" 2>/dev/null)" in "217:"*) rm -- "$HEAVY_LOCK";; esac' EXIT
export FDA_HEAVY_SLOT="$HEAVY_LOCK"
export PATH="$S/bin:$PATH" FDA_KNOWLEDGE=/home/brendan/Claude_sandbox/_worktrees/230-kb-pin FDA_PROMPTS_DIR=/home/brendan/Claude_sandbox/_worktrees/230-kb-pin/prompts
export FDA_REPAIR_RECORDS=/home/brendan/Claude_sandbox/_worktrees/217-kb/repairs/records
BEFORE=$(ls -1 runs | grep '^2026' | sort | tail -1)
t0=$(date +%s)
timeout -k 60 10800 systemd-run --user --scope -q -p MemoryMax=7G nice -n 15 \
  "$PY" -m agent run "results/213_repair_feedback/designs/$ID/spec.md" --name "$ID" --board kr260 --review off --interview off --verif-level V2 \
  --stop-after 2 --harness claude_code --cc-model claude-sonnet-5-5 --cc-effort medium --max-usd 12 --budget-scale 3.5 --harness-arm "H1,R1,R2,R4" >> "$LOG" 2>&1
rc=$?; t1=$(date +%s)
echo "$(date '+%F %T') exit $rc wall_s=$((t1-t0))" >> "$LOG"
RID=$(ls -1 runs | grep '^2026' | sort | tail -1)
D="results/217_repair_memory/live/${ID}"; mkdir -p "$D"
if [ "$RID" = "$BEFORE" ] || [ ! -f "runs/$RID/summary.json" ]; then echo "no run record (exit $rc)" > "$D/NO_RECORD.txt"; cp "$LOG" "$D/driver.log"; exit 9; fi
R="runs/$RID"
cp "$R/summary.json" "$R/role_usage.jsonl" "$R/routing_events.jsonl" "$R/config.json" "$D/" 2>/dev/null
cp -r "$R/repair_memory" "$D/" 2>/dev/null
echo "$RID" > "$D/RUN_ID.txt"; echo "H1,R1,R2,R4 exit=$rc wall_s=$((t1-t0)) weekly_before=${pct}%" > "$D/meta.txt"
cp "$LOG" "$D/driver.log"
exit 0
