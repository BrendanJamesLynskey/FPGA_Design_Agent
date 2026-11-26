#!/usr/bin/env bash
# Brief 224, second arm "224-arm2-long-output": the 209 pilot's driver adapted (same model, endpoint, --max-usd 12, --budget-scale 3.5, V2, board kr260),
# run on the agent with streaming, the larger writing-role limit and file-by-file writing. Usage: run_agent.sh <id> <k>   (k = 1..3)
# Never a first-time result: every run of this arm is an intervention on a design that failed in the pilot.
set -uo pipefail
ID="${1:?id}"; K="${2:?k}"
ROOT=/home/brendan/Claude_sandbox/_worktrees/224-long-output
H=/home/brendan/Claude_sandbox/_handoff
PY=/home/brendan/Claude_sandbox/FPGA_Design_Agent/.venv/bin/python
cd "$ROOT"
mkdir -p runs/_logs runs/_locks
LOG="runs/_logs/arm2_${ID}_r${K}.log"
{ echo "start $(date '+%F %T')"; git rev-parse HEAD; git log -1 --format=%s; } > "$LOG"
TEXT="224: $ID arm2 run $K, $(date +%H:%M), expected end +90min, peak 6G, Vivado impl"
HEAVY=""
until HEAVY="$("$H/take_heavy_slot.sh" "$TEXT")"; do sleep 120; done
echo "slot $HEAVY taken $(date '+%F %T')" >> "$LOG"
trap 'case "$(cat "$HEAVY" 2>/dev/null)" in "224:"*) rm -- "$HEAVY";; esac' EXIT
export FDA_KNOWLEDGE="${FDA_KNOWLEDGE:-/home/brendan/Claude_sandbox/_worktrees/224-kb}"
export FDA_HEAVY_LOCK="$ROOT/runs/_locks/arm2_${ID}_r${K}.heavy_slot.lock"
systemd-run --user --scope -q -p MemoryMax=7G nice -n 15 \
  "$PY" -m agent run "pilots/224/$ID/spec.md" --name "$ID" --board kr260 --review off --interview off --verif-level V2 --max-usd 12 --budget-scale 3.5 \
  --model-config '{"default": {"endpoint": "anthropic_api", "model": "claude-sonnet-5-5"}}' >> "$LOG" 2>&1
echo "exit $? $(date '+%F %T')" >> "$LOG"
