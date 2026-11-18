#!/usr/bin/env bash
# Brief 97C: build one of control | agent_both | all3 through the flow under the heavy-slot rule (one slot, FDA_VIVADO_THREADS=1, run_vivado.sh puts Vivado in a
# systemd scope with MemoryMax=6G), then record the digest (timing, utilisation, power, gates) and the wall time in results/b97c/builds/<name>/.
#   results/b97c/build_one.sh <name> [wait minutes, default 300]
set -uo pipefail
V="${1:?control|agent_both|all3}"; WAIT="${2:-300}"
ROOT=/home/brendan/Claude_sandbox/_worktrees/97c-seq
H=/home/brendan/Claude_sandbox/_handoff
cd "$ROOT"
if [ "$V" = control ]; then D=designs/b96_kr260_10g; else D=designs/b96_kr260_10g/lat_$V; fi
TEXT="97C: Vivado impl $V peak 6G, $(date +%H:%M), expected end $(date -d '+45 min' +%H:%M)"
n=0
while true; do
  out="$("$H/take_heavy_slot.sh" --env "$TEXT" 2>/dev/null)" && [ -n "$out" ] && { eval "$out"; break; }
  n=$((n+1)); [ "$n" -ge "$WAIT" ] && { echo "no heavy slot within $WAIT minutes"; exit 1; }
  read -r -t 60 < <(tail -f /dev/null) || true
done
release() { case "$(cat "$HEAVY_LOCK" 2>/dev/null)" in "97C:"*) rm -f "$HEAVY_LOCK";; esac; }
trap release EXIT
export FDA_VIVADO_THREADS=1 FDA_VIVADO_MAX=3
OUT="$ROOT/results/b97c/builds/$V"; mkdir -p "$OUT"
echo "slot $HEAVY_LOCK taken: $(cat "$HEAVY_LOCK"); threads $FDA_VIVADO_THREADS"
T0=$(date +%s); date -Is > "$OUT/started.txt"
flow/run_vivado.sh "$D" base 2>&1 | tail -40 | tee "$OUT/run_vivado.log"
T1=$(date +%s); echo "wall_s $((T1-T0))" > "$OUT/wall.txt"
B="$D/build/base"
[ -f "$B/post_route.dcp" ] || { echo "no post_route.dcp: build failed"; exit 2; }
python3 - "$B" "$OUT" <<'PY'
import json, sys
from pathlib import Path
from flow.digest.build import digest_build
b, out = Path(sys.argv[1]), Path(sys.argv[2])
d = digest_build(b)
keep = {k: d.get(k) for k in ("timing", "utilization", "power", "gates", "drc", "methodology")}
(out / "digest.json").write_text(json.dumps(keep, indent=1, default=str) + "\n")
print(json.dumps(keep["timing"], default=str)[:600])
PY
cp "$B/run.json" "$OUT/run.json" 2>/dev/null || true
ls "$B"/*.bit
