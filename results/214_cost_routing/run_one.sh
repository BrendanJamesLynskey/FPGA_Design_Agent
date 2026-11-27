#!/usr/bin/env bash
# Brief 214 A/B: one agent run of one pilot design in one arm, stages 0 to 2. Usage: run_one.sh <n> <design> <k> <arm>   (arm: control | routing | routing_kway)
# Preflight (pinned CLI, weekly usage, stop flag), a heavy slot (stage 2 runs a Vivado synthesis), a memory-capped scope, a record after the run.
# Exit codes: 0 record written; 3 stop flag; 4 CLI mismatch; 5 usage at/over the stop; 6 no slot yet (caller retries); 9 run produced no record.
set -uo pipefail
N="${1:?n}"; ID="${2:?design}"; K="${3:?k}"; ARM="${4:?arm}"
ROOT=/home/brendan/Claude_sandbox/_worktrees/214-cost-routing
S=/home/brendan/Claude_sandbox/_scratch_214; C=/home/brendan/Claude_sandbox/_scratch_213; H=/home/brendan/Claude_sandbox/_handoff
PY=/home/brendan/Claude_sandbox/FPGA_Design_Agent/.venv/bin/python
STOP_AT="${FDA_STOP_PCT:-92}"
cd "$ROOT"; mkdir -p "$S/logs" results/214_cost_routing/runs
LOG="$S/logs/${N}_${ID}_k${K}_${ARM}.log"
[ -e "$S/STOP" ] && { echo "STOP flag set" | tee -a "$LOG"; exit 3; }
[ "$N" -gt "${FDA_LAST_RUN:-12}" ] && { echo "run $N beyond the cap of 12 runs (usage and slot budget): not started" | tee -a "$LOG"; exit 3; }
ver=$("$C/bin/claude" --version | cut -d' ' -f1)
[ "$ver" = 2.1.321 ] && [ "$(sha256sum "$C/bin/claude" | cut -d' ' -f1)" = "$(cat "$C/bin/claude.sha256")" ] || { echo "PREFLIGHT_FAIL $N: CLI $ver" | tee -a "$LOG"; touch "$S/STOP"; exit 4; }
pct=$("$H/usage_check.sh" 2>&1 | grep 'Current week (all models)' | grep -o '[0-9]*% used' | head -1 | tr -d '%used ')
echo "$(date '+%F %T') run $N $ID k$K $ARM weekly_before=${pct}%" | tee -a "$LOG"
[ "${pct:-100}" -ge "$STOP_AT" ] && { echo "weekly usage >= $STOP_AT: stop (BLOCKED)" | tee -a "$LOG"; touch "$S/STOP"; exit 5; }
TEXT="214: A/B run $N $ID k$K $ARM, stage 2 (Vivado synth), $(date +%H:%M), expected end +60min, peak 4G"
if ! eval "$("$H/take_heavy_slot.sh" --env "$TEXT")" 2>/dev/null || [ -z "${HEAVY_LOCK:-}" ]; then echo "no slot yet" >> "$LOG"; exit 6; fi
echo "$(date '+%F %T') slot $HEAVY_LOCK" >> "$LOG"
trap 'case "$(cat "$HEAVY_LOCK" 2>/dev/null)" in "214:"*) rm -- "$HEAVY_LOCK";; esac' EXIT
export FDA_HEAVY_SLOT="$HEAVY_LOCK"
export PATH="$C/bin:$PATH" FDA_KNOWLEDGE=/home/brendan/Claude_sandbox/_worktrees/kb-prompts-pin FDA_PROMPTS_DIR=/home/brendan/Claude_sandbox/_worktrees/kb-prompts-pin/prompts
case "$ARM" in control) HA=(--harness-arm H1);; routing) HA=(--harness-arm H1 --routing on);; routing_kway) HA=(--harness-arm H1 --routing on --kway 3);; *) echo "bad arm"; exit 2;; esac
BEFORE=$(ls -1 runs | grep '^2026' | sort | tail -1)
t0=$(date +%s)
timeout -k 60 10800 systemd-run --user --scope -q -p MemoryMax=7G nice -n 15 \
  "$PY" -m agent run "results/214_cost_routing/designs/$ID/spec.md" --name "$ID" --board kr260 --review off --interview off --verif-level V2 \
  --stop-after 2 --harness claude_code --cc-model claude-sonnet-5-5 --cc-effort medium --max-usd 12 --budget-scale 3.5 "${HA[@]}" >> "$LOG" 2>&1
rc=$?; t1=$(date +%s)
echo "$(date '+%F %T') exit $rc wall_s=$((t1-t0))" >> "$LOG"
RID=$(grep -o '"run_id": "20[0-9-]*[0-9a-f]*"' "$LOG" | tail -1 | cut -d'"' -f4)
D="results/214_cost_routing/runs/${N}_${ID}_k${K}_${ARM}"; mkdir -p "$D"
if [ -z "$RID" ] || [ ! -f "runs/$RID/summary.json" ]; then echo "no run record (exit $rc)" > "$D/NO_RECORD.txt"; cp "$LOG" "$D/driver.log"; exit 9; fi
R="runs/$RID"
cp "$R/summary.json" "$R/role_usage.jsonl" "$R/routing_events.jsonl" "$R/config.json" "$R/kway.jsonl" "$D/" 2>/dev/null
for f in "$R/$ID"/rtl "$R/$ID"/tests "$R/$ID"/verif; do [ -d "$f" ] && cp -r "$f" "$D/"; done
cp "$R/$ID/model.py" "$R/$ID/spec.yaml" "$D/" 2>/dev/null
echo "$RID" > "$D/RUN_ID.txt"; echo "$ARM ${HA[*]} exit=$rc wall_s=$((t1-t0)) weekly_before=${pct}%" > "$D/meta.txt"
pct2=$("$H/usage_check.sh" 2>&1 | grep 'Current week (all models)' | grep -o '[0-9]*% used' | head -1 | tr -d '%used '); echo "weekly_after=${pct2}%" >> "$D/meta.txt"
cp "$LOG" "$D/driver.log"
exit 0
