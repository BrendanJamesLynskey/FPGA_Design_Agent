#!/usr/bin/env bash
# Brief 230 labelled arm: brief 224's run_agent.sh with this branch (same model, endpoint, --max-usd 12, --budget-scale 3.5, V2, board kr260).
# Usage: run_agent.sh <id> <k>   (k = 1..3). The knowledge pin is the control's (5e2eab8), so the arms differ only in the agent.
set -uo pipefail
ID="${1:?id}"; K="${2:?k}"
ROOT=/home/brendan/Claude_sandbox/_worktrees/230-constraints-complete
H=/home/brendan/Claude_sandbox/_handoff
PY=/home/brendan/Claude_sandbox/FPGA_Design_Agent/.venv/bin/python
cd "$ROOT"
mkdir -p runs/_logs
LOG="runs/_logs/arm_${ID}_r${K}.log"
{ echo "start $(date '+%F %T')"; git rev-parse HEAD; git log -1 --format=%s; } > "$LOG"
TEXT="230: $ID arm run $K, $(date +%H:%M), expected end +90min, peak 6G, Vivado impl"
until eval "$("$H/take_heavy_slot.sh" --env "$TEXT" 2>/dev/null)" && [ -n "${HEAVY_LOCK:-}" ]; do sleep 120; done
export FDA_HEAVY_SLOT="$HEAVY_LOCK"
export FDA_VIVADO_MAX=2   # take_heavy_slot.sh admitted this job, possibly beside another Vivado one (house rules: two heavy slots)
echo "slot $HEAVY_LOCK taken $(date '+%F %T')" >> "$LOG"
trap 'case "$(cat "$HEAVY_LOCK" 2>/dev/null)" in "230:"*) rm -- "$HEAVY_LOCK";; esac' EXIT
export FDA_KNOWLEDGE="${FDA_KNOWLEDGE:-/home/brendan/Claude_sandbox/_worktrees/230-kb-pin}"
systemd-run --user --scope -q -p MemoryMax=7G nice -n 15 \
  "$PY" -m agent run "pilots/230/$ID/spec.md" --name "$ID" --board kr260 --review off --interview off --verif-level V2 --max-usd 12 --budget-scale 3.5 \
  --model-config '{"default": {"endpoint": "anthropic_api", "model": "claude-sonnet-5-5"}}' >> "$LOG" 2>&1
echo "exit $? $(date '+%F %T')" >> "$LOG"
