#!/bin/bash
# run_one.sh <problem id> <tag>   -- one brief-215 agent run on one CVDP problem (stages 0-2, simulation only, no Vivado, no slot).
# Preflight (every launch): stop flag, pinned Claude Code version, weekly usage, load under 6, more than 12 GB free.
# Logs to $S/logs/<tag>.log; the design lands in the worktree's runs/<run id>/ (RUN_ID.txt in $S/runs/<tag>/).
set -u
S=/home/brendan/Claude_sandbox/_scratch_215; H=/home/brendan/Claude_sandbox/_handoff
W=/home/brendan/Claude_sandbox/_worktrees/215-public-benchmarks
DATA=${CVDP_DATA:?set CVDP_DATA to the non-agentic jsonl}
MODEL=${CC_MODEL:-claude-sonnet-5-5}; WALL=${WALL_S:-3600}
pid=$1; tag=$2
mkdir -p $S/logs $S/runs/$tag; L=$S/logs/$tag.log
[ -e $S/STOP ] && { echo "STOP flag set" | tee -a $L; exit 3; }
ver=$($S/bin/claude --version | cut -d' ' -f1)
[ "$ver" = 2.1.321 ] || { echo "PREFLIGHT_FAIL $tag: CLI $ver" | tee -a $L; touch $S/STOP; exit 4; }
pct=$($H/usage_check.sh 2>&1 | grep 'Current week (all models)' | grep -o '[0-9]*% used' | head -1 | tr -d '%used ')
echo "$(date '+%F %T') $tag problem=$pid model=$MODEL weekly_before=${pct}%" | tee -a $L
[ "${pct:-100}" -ge 60 ] && { echo "weekly usage >= 60: stop (brief 215)" | tee -a $L; touch $S/STOP; exit 5; }
load=$(cut -d' ' -f1 /proc/loadavg); free_gb=$(free -g | awk '/^Mem:/{print $7}')
echo "$(date '+%F %T') load=$load available_gb=$free_gb" | tee -a $L
awk -v l=$load 'BEGIN{exit !(l<6)}' && [ "$free_gb" -gt 12 ] || { echo "WAIT_RESOURCES $tag" | tee -a $L; exit 6; }
python3 $W/tools/public_bench/cvdp_adapter.py prepare --data $DATA --id $pid --out $S/runs/$tag/in >> $L 2>&1 || exit 7
cd $W || exit 8
export PATH=$S/bin:$PATH FDA_KNOWLEDGE=/home/brendan/Claude_sandbox/_worktrees/215-kb FDA_PROMPTS_DIR=/home/brendan/Claude_sandbox/_worktrees/215-kb/prompts
t0=$(date +%s)
timeout -k 30 $WALL systemd-run --user --scope -q -p MemoryMax=6G nice -n 15 \
  /home/brendan/Claude_sandbox/FPGA_Design_Agent/.venv/bin/python -m agent run $S/runs/$tag/in/spec.md --stop-after 2 --no-shell \
  --verif-level V1 --harness claude_code --cc-model $MODEL --cc-effort medium --max-usd 3 --budget-scale 2 --name ${tag} >> $L 2>&1
rc=$?; t1=$(date +%s)
echo "$(date '+%F %T') exit $rc wall_s=$((t1-t0))" | tee -a $L
pct2=$($H/usage_check.sh 2>&1 | grep 'Current week (all models)' | grep -o '[0-9]*% used' | head -1 | tr -d '%used ')
echo "$(date '+%F %T') weekly_after=${pct2}%" | tee -a $L
