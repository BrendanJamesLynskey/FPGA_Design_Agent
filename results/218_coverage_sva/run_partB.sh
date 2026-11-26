#!/usr/bin/env bash
# Brief 218 Part B: one agent run of one pilot design in one arm (pre-registered in preregistration.md). Usage: run_partB.sh <design> <A0|A1>
#   A0 = today's V3 (--coverage-loop off); A1 = the loop (--coverage-loop on). Everything else is the same.
# NOT RUN in the executor session that wrote it: a run starts the agent, whose access gate needs the owner's key file in the worktree
# (house rules: `cp ~/Claude_sandbox/FPGA_Design_Agent/.env <worktree>/.env`, never cat it), and that session's instructions said never to touch .env.
# Whoever runs it (the planner, or this executor once told to) copies that file first and deletes the copy afterwards.
# The slot, the memory cap and the private FDA_HEAVY_LOCK follow the 209 pilot's run_agent.sh (brief 219's FDA_HEAVY_SLOT replaces the private lock once PR #344 merges).
set -uo pipefail
ID="${1:?design: p1_clkmeter | p2_bram_rom | p3_crc_engine}"; ARM="${2:?arm: A0 | A1}"
ROOT=/home/brendan/Claude_sandbox/_worktrees/218-coverage-sva
H=/home/brendan/Claude_sandbox/_handoff
PY=/home/brendan/Claude_sandbox/FPGA_Design_Agent/.venv/bin/python
LIVE=/home/brendan/Claude_sandbox/_worktrees/218-kb        # the knowledge checkout at the commit prompts_pin.json pins (prompts only)
cd "$ROOT"
mkdir -p runs/_logs runs/_locks
LOG="runs/_logs/218_${ID}_${ARM}.log"
{ echo "start $(date '+%F %T')"; git rev-parse HEAD; } > "$LOG"
# preflight (eval_run_checklist step 3): the pinned CLI, else no record and no slot
V="$(claude --version | awk '{print $1}')"
if [ "$V" != "2.1.321" ]; then echo "PREFLIGHT_FAIL claude $V" | tee -a "$LOG"; exit 3; fi
test -f .env || { echo "PREFLIGHT_FAIL no .env in the worktree (see the header)" | tee -a "$LOG"; exit 3; }
FLAG=off; [ "$ARM" = "A1" ] && FLAG=on
TEXT="218: $ID $ARM agent run, $(date +%H:%M), expected end +90min, peak 4G, Vivado impl"
HEAVY=""
until HEAVY="$("$H/take_heavy_slot.sh" "$TEXT")"; do sleep 120; done
echo "slot $HEAVY taken $(date '+%F %T')" >> "$LOG"
trap 'case "$(cat "$HEAVY" 2>/dev/null)" in "218:"*) rm -f "$HEAVY";; esac' EXIT
export FDA_PROMPTS_DIR="$LIVE/prompts" FDA_KNOWLEDGE="$LIVE"
export FDA_HEAVY_LOCK="$ROOT/runs/_locks/218_${ID}_${ARM}.heavy_slot.lock"
systemd-run --user --scope -q -p MemoryMax=6G nice -n 15 \
  "$PY" -m agent run "pilots/209/$ID/spec.md" --name "${ID}_${ARM}" --board kr260 --review off --interview off --verif-level V3 --stop-after 2 \
  --harness claude_code --cc-model claude-sonnet-5-5 --max-usd 12 --budget-scale 3.5 --coverage-loop "$FLAG" >> "$LOG" 2>&1
echo "exit $? $(date '+%F %T')" >> "$LOG"
