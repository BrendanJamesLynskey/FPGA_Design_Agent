#!/usr/bin/env bash
# formal.sh: run every SymbiYosys job of a design (bmc + cover) into build/verif/formal/<job>_<task>/.
#   flow/formal.sh designs/t1_dimmer_counter
# Needs sby, yosys 0.33+ and z3 on PATH (CI: apt; locally: source ~/.local/opt/formal-deb/env.sh).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
D="${1:?design folder}"
OUT="$ROOT/build/verif/formal"
rm -rf "$OUT"; mkdir -p "$OUT"
cd "$ROOT/$D/verif/formal"
for f in *.sby; do
  job="${f%.sby}"
  for task in bmc cover; do
    sby -f -d "$OUT/${job}_${task}" "$f" "$task" >"$OUT/${job}_${task}.log" 2>&1 || true
    echo "formal ${job}_${task}: $(head -1 "$OUT/${job}_${task}/status" 2>/dev/null || echo ABSENT)"
  done
done
