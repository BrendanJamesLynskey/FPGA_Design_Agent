#!/usr/bin/env bash
# Brief 209 (209b agent: real-dollar cap 12, budget scale 3.5): one agent run of one pilot design, from the unchanged spec. Usage: run_agent.sh <id> <k>   (k = 1..3)
# Takes a heavy slot (waits while none is free), runs under a memory-capped scope with a private FDA_HEAVY_LOCK, logs to runs/_logs/.
set -uo pipefail
ID="${1:?id}"; K="${2:?k}"
ROOT=/home/brendan/Claude_sandbox/_worktrees/209-kr260-pilot
H=/home/brendan/Claude_sandbox/_handoff
PY=/home/brendan/Claude_sandbox/FPGA_Design_Agent/.venv/bin/python
cd "$ROOT"
mkdir -p runs/_logs runs/_locks
LOG="runs/_logs/${ID}_r${K}.log"
{ echo "start $(date '+%F %T')"; git rev-parse HEAD; git log -1 --format=%s; } > "$LOG"
TEXT="209: $ID agent run $K, $(date +%H:%M), expected end +90min, peak 6G, Vivado impl"
HEAVY=""
until HEAVY="$("$H/take_heavy_slot.sh" "$TEXT")"; do sleep 120; done
echo "slot $HEAVY taken $(date '+%F %T')" >> "$LOG"
trap 'case "$(cat "$HEAVY" 2>/dev/null)" in "209:"*) rm -f "$HEAVY";; esac' EXIT
export FDA_KNOWLEDGE="${FDA_KNOWLEDGE:-/home/brendan/Claude_sandbox/_worktrees/209-kb}"
export FDA_HEAVY_LOCK="$ROOT/runs/_locks/${ID}_r${K}.heavy_slot.lock"
systemd-run --user --scope -q -p MemoryMax=7G nice -n 15 \
  "$PY" -m agent run "pilots/209/$ID/spec.md" --name "$ID" --board kr260 --review off --interview off --verif-level V2 --max-usd 12 --budget-scale 3.5 \
  --model-config '{"default": {"endpoint": "anthropic_api", "model": "claude-sonnet-5-5"}}' >> "$LOG" 2>&1
echo "exit $? $(date '+%F %T')" >> "$LOG"
