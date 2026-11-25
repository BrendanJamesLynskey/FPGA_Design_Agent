#!/bin/bash
# usage: chain.sh <arm>:<spec> ...
cd "$(git rev-parse --show-toplevel)"
S=${SCRATCH:?set SCRATCH to a scratch directory for the logs}
export PYTHONPATH=.   # FDA_PROMPTS_DIR must point at the pinned private prompts
PY=${PY:-python}
for j in "$@"; do arm=${j%%:*}; sp=${j##*:}
  timeout 1500 $PY results/150_ip_lookup/stage1_trial/run_arm.py $arm run results/150_ip_lookup/stage1_trial/specs/$sp/spec.md --name t150_${sp}_$arm --interview off --stop-after 1 --harness claude_code --cc-model claude-haiku-5-5 --max-usd 1.0 > $S/${sp}_$arm.log 2>&1
  echo "$sp $arm exit $? $(date +%T)" >> $S/chain.status
done
