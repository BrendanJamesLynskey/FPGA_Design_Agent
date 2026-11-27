#!/usr/bin/env bash
# Brief 230 arm: copy one finished run's records into pilots/230/<id>/arm_run<k>/ and append the ledger line.  record_one.sh <id> <k> <run id>
set -uo pipefail
ID="$1"; K="$2"; RID="$3"
ROOT=/home/brendan/Claude_sandbox/_worktrees/230-constraints-complete; cd "$ROOT"
PY=/home/brendan/Claude_sandbox/FPGA_Design_Agent/.venv/bin/python
R=runs/$RID; D=pilots/230/$ID/arm_run$K; DD=$R/$ID; LED=pilots/230/cost_ledger.tsv
SHA=$(git rev-parse HEAD | cut -c1-12)
mkdir -p "$D"
PYTHONPATH=. $PY pilots/230/record_run.py "$R" "$ID" "$K" "runs/_logs/arm_${ID}_r${K}.log" "$SHA" > "$D/record_stdout.txt" 2>&1
cp $R/summary.json $R/role_usage.jsonl $R/model_calls.jsonl $R/config.json $R/run_record.json "$D/" 2>/dev/null
cp runs/_logs/arm_${ID}_r${K}.log "$D/agent_stdout.log"
for f in build/trace/trace.md build/trace/trace.json build/base/manifest.json build/base/run.json build/base/timing_summary.rpt build/base/utilization.rpt build/base/prepare.json build/base/known_pre.xdc build/base/known_post.xdc build/base/check_timing_synth.rpt build/verif/verif_gates.json build/architecture.json; do [ -f "$DD/$f" ] && { mkdir -p "$D/$(dirname $f)"; cp "$DD/$f" "$D/$f"; }; done
rsync -a --exclude build --exclude spec.md --exclude __pycache__ --exclude sim_build "$DD/" "$D/design/" 2>/dev/null
python3 - "$ID" "$K" "$RID" "$SHA" "$D/run_record.json" >> "$LED" <<'PY'
import json,sys
i,k,rid,sha,p=sys.argv[1:6]; d=json.load(open(p))
print("\t".join(map(str,[i,k,rid,sha,d.get("real_usd"),d.get("tokens_total"),d.get("truncated_calls"),(d.get("outcome") or "")[:110].replace("\t"," ")])))
PY
