#!/bin/bash
# Brief 239: one re-measure run (a cell of prereg.md): the flags of brief 227's arm A on a pilot design, stages 0 to 2, Claude Code on the plan.
#   run_cell.sh <design> <k>
# Needs: the pinned CLI in _scratch_227/bin (version 2.1.321), the pilot inputs in _scratch_227/pilots/<design>/{spec.md,data/}, the knowledge bank
# checkout at the pin in KB (default _worktrees/230-kb-pin), the worktree's .env (the access key; copied by hand, never read or printed).
# The stage-2 gate builds the rtl stage in Vivado (about 2 minutes, 4 GB), so each run holds a heavy slot (take_heavy_slot.sh) for its whole length.
set -u
D=$1; K=$2
S=/home/brendan/Claude_sandbox/_scratch_227; O=/home/brendan/Claude_sandbox/_scratch_239; H=/home/brendan/Claude_sandbox/_handoff
W=/home/brendan/Claude_sandbox/_worktrees/239-stage2; KB=${KB:-/home/brendan/Claude_sandbox/_worktrees/kb-prompts-pin}
TAG=b239_${D}_r${K}; L=$O/logs/$TAG.log; mkdir -p $O/logs
[ -e $O/STOP ] && { echo "STOP flag set" | tee -a $L; exit 3; }
ver=$($S/bin/claude --version | cut -d' ' -f1)
[ "$ver" = 2.1.321 ] || { echo "PREFLIGHT_FAIL $TAG: CLI $ver" | tee -a $L; touch $O/STOP; exit 4; }
pct=$($H/usage_check.sh 2>&1 | grep 'Current week (all models)' | grep -o '[0-9]*% used' | head -1 | tr -d '%used ')
echo "$(date '+%F %T') $TAG weekly_before=${pct}%" | tee -a $L
[ "${pct:-100}" -ge 92 ] && { echo "weekly usage >= 92: stop" | tee -a $L; touch $O/STOP; exit 5; }
# a heavy slot for the run (poll; the fair queue needs the caller to keep polling)
end=$(date -d '+50 min' +%H:%M); got=""
for try in $(seq 1 720); do
  [ -e $O/STOP ] && { echo "STOP flag set" | tee -a $L; exit 3; }
  load=$(cut -d' ' -f1 /proc/loadavg); free_gb=$(free -g | awk '/^Mem:/{print $7}')
  if awk -v l=$load 'BEGIN{exit !(l<6)}' && [ "$free_gb" -gt 12 ]; then
    got=$($H/take_heavy_slot.sh "239: agent run $TAG, stage 0-2 with the rtl Vivado gate, $(date +%H:%M), expected end $end, peak 4G, Vivado synth" 2>/dev/null) && [ -n "$got" ] && break
  fi
  [ $((try % 10)) -eq 1 ] && echo "$(date '+%F %T') WAIT_SLOT $TAG load=$load free=$free_gb" | tee -a $L
  sleep 60
done
[ -n "$got" ] || { echo "NO_SLOT $TAG" | tee -a $L; exit 6; }
echo "$(date '+%F %T') slot taken: $got" | tee -a $L
release() { case "$(cat $got 2>/dev/null)" in "239:"*) rm -f -- "$got";; esac; }
trap release EXIT
IN=$S/pilots/$D
cd $W || exit 8
export PATH=$S/bin:$PATH FDA_KNOWLEDGE=$KB FDA_PROMPTS_DIR=$KB/prompts
t0=$(date +%s)
timeout -k 30 3300 systemd-run --user --scope -q -p MemoryMax=6G nice -n 15 \
  /home/brendan/Claude_sandbox/FPGA_Design_Agent/.venv/bin/python -m agent run $IN/spec.md --stop-after 2 --verif-level V2 --spec-tests \
  --harness claude_code --cc-model claude-sonnet-5-5 --cc-effort medium --board kr260 --review off --docs off --max-usd 12 --budget-scale 3.5 \
  --interview off --requirements loose --name $TAG >> $L 2>&1
rc=$?; t1=$(date +%s)
echo "$(date '+%F %T') exit $rc wall_s=$((t1-t0))" | tee -a $L
pct2=$($H/usage_check.sh 2>&1 | grep 'Current week (all models)' | grep -o '[0-9]*% used' | head -1 | tr -d '%used ')
echo "$(date '+%F %T') weekly_after=${pct2}%" | tee -a $L
