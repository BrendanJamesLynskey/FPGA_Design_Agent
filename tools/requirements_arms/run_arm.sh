#!/bin/bash
# Brief 227: one build run of an arm on a pilot design, stages 0 to 2 (simulation only: no Vivado, no slot), Claude Code on the plan.
#   run_arm.sh <A|B|C> <design> <k>
# A: the request as the user wrote it, nobody to ask (--interview off, --requirements loose).
# B: the readiness gate with an oracle that answers from the hidden spec (--interview oracle --readiness on); the build follows only if the set was frozen.
# C: given requirements: the request and the further answers as one document, no interview (--interview off): stage 0 is bypassed.
# Needs: SCRATCH (default /home/brendan/Claude_sandbox/_scratch_227) holding bin/claude (the pinned CLI), pilots/<design>/{spec.md,hidden_spec.md,data/}.
set -u
ARM=$1; D=$2; K=$3
S=${SCRATCH:-/home/brendan/Claude_sandbox/_scratch_227}; H=/home/brendan/Claude_sandbox/_handoff
W=${WORKTREE:-/home/brendan/Claude_sandbox/_worktrees/227-requirements-readiness}
TAG=b227_${ARM}_${D}_r${K}; L=$S/logs/$TAG.log; mkdir -p $S/logs
[ -e $S/STOP ] && { echo "STOP flag set" | tee -a $L; exit 3; }
ver=$($S/bin/claude --version | cut -d' ' -f1)
[ "$ver" = 2.1.321 ] || { echo "PREFLIGHT_FAIL $TAG: CLI $ver" | tee -a $L; touch $S/STOP; exit 4; }
pct=$($H/usage_check.sh 2>&1 | grep 'Current week (all models)' | grep -o '[0-9]*% used' | head -1 | tr -d '%used ')
echo "$(date '+%F %T') $TAG weekly_before=${pct}%" | tee -a $L
[ "${pct:-100}" -ge 90 ] && { echo "weekly usage >= 90: stop (owner plan 2026-11-26: stop at 92)" | tee -a $L; touch $S/STOP; exit 5; }
load=$(cut -d' ' -f1 /proc/loadavg); free_gb=$(free -g | awk '/^Mem:/{print $7}')
awk -v l=$load 'BEGIN{exit !(l<6)}' && [ "$free_gb" -gt 12 ] || { echo "WAIT_RESOURCES $TAG load=$load free=$free_gb" | tee -a $L; exit 6; }
IN=$S/pilots/$D; FLAGS="--interview off --requirements loose"
if [ "$ARM" = C ]; then mkdir -p $S/pilots/${D}_C && cp -r $IN/data $S/pilots/${D}_C/ 2>/dev/null; cp $IN/hidden_spec.md $S/pilots/${D}_C/spec.md; IN=$S/pilots/${D}_C; fi
[ "$ARM" = B ] && FLAGS="--interview oracle --oracle claude_code --oracle-cc-model claude-sonnet-5-5 --hidden-spec $IN/hidden_spec.md --readiness on --requirements loose"
cd $W || exit 8
export PATH=$S/bin:$PATH FDA_KNOWLEDGE=/home/brendan/Claude_sandbox/_worktrees/227-kb-skill FDA_PROMPTS_DIR=/home/brendan/Claude_sandbox/_worktrees/227-kb/prompts
t0=$(date +%s)
timeout -k 30 3300 systemd-run --user --scope -q -p MemoryMax=6G nice -n 15 \
  /home/brendan/Claude_sandbox/FPGA_Design_Agent/.venv/bin/python -m agent run $IN/spec.md --stop-after 2 --no-shell --verif-level V2 \
  --harness claude_code --cc-model claude-sonnet-5-5 --cc-effort medium --board kr260 --review off --docs off --max-usd 8 --budget-scale 3 $FLAGS --name $TAG >> $L 2>&1
rc=$?; t1=$(date +%s)
echo "$(date '+%F %T') exit $rc wall_s=$((t1-t0))" | tee -a $L
pct2=$($H/usage_check.sh 2>&1 | grep 'Current week (all models)' | grep -o '[0-9]*% used' | head -1 | tr -d '%used ')
echo "$(date '+%F %T') weekly_after=${pct2}%" | tee -a $L
