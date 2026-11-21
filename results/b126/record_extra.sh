#!/usr/bin/env bash
# Brief 126: copy the CDC summary table, the methodology summary and the stamp of a finished build into results/b126/builds/<name>/ (build_one.sh records the digest and run.json).
#   results/b126/record_extra.sh rm_gp_bypass|rm_gp
set -euo pipefail
V="$1"; R="$(cd "$(dirname "$0")/../.." && pwd)"; B="$R/designs/b96_kr260_10g/$V/build/base"; O="$R/results/b126/builds/$V"
sed -n '/^CDC Report/,/^$/p;/^ID .*Severity/,/^$/p' "$B/cdc.rpt" | head -30 > "$O/cdc_summary.txt"
grep -E "^\| *[A-Z]+-[0-9]+|Rule|Severity" "$B/methodology.rpt" | head -20 > "$O/methodology_summary.txt" || true
python3 - "$B" "$O" <<'PY'
import json, sys
b, o = sys.argv[1:]
r = json.load(open(f"{b}/run.json")); g = json.load(open(f"{b}/gates.json"))
open(f"{o}/stamp.txt", "w").write(f"{r.get('build_stamp')} sources_sha256 {r.get('sources_sha256')} commit {r.get('git_commit')} dirty {r.get('git_dirty')}\n")
PY
