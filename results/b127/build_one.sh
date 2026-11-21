#!/usr/bin/env bash
# Brief 127: build rm_gp_itch (the KR260 10G design with the standard-protocol trading path) through the flow under the heavy-slot rule (a slot taken with take_heavy_slot.sh, FDA_VIVADO_THREADS from the
# slot's answer, run_vivado.sh puts Vivado in a systemd scope with MemoryMax=6G), then record the digest (timing, utilisation, power, gates), the in-context report_cdc summary and the wall time in
# results/b127/builds/<name>/.   results/b127/build_one.sh [name, default rm_gp_itch] [wait minutes, default 300]
set -uo pipefail
V="${1:-rm_gp_itch}"; WAIT="${2:-300}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
H=/home/brendan/Claude_sandbox/_handoff
cd "$ROOT"
D=designs/b96_kr260_10g/$V
TEXT="127: Vivado impl $V peak 6G, $(date +%H:%M), expected end $(date -d '+50 min' +%H:%M)"
n=0
while true; do
  out="$("$H/take_heavy_slot.sh" --env "$TEXT" 2>/dev/null)" && [ -n "$out" ] && { eval "$out"; break; }
  n=$((n+1)); [ "$n" -ge "$WAIT" ] && { echo "no heavy slot within $WAIT minutes"; exit 1; }
  read -r -t 60 < <(tail -f /dev/null) || true
done
release() { case "$(cat "$HEAVY_LOCK" 2>/dev/null)" in "127:"*) rm -f "$HEAVY_LOCK";; esac; }
trap release EXIT
export FDA_VIVADO_THREADS=1 FDA_VIVADO_MAX=3
OUT="$ROOT/results/b127/builds/$V"; mkdir -p "$OUT"
echo "slot $HEAVY_LOCK taken: $(cat "$HEAVY_LOCK"); threads $FDA_VIVADO_THREADS"
T0=$(date +%s); date -Is > "$OUT/started.txt"; git rev-parse HEAD > "$OUT/commit.txt"; git status --porcelain -- designs flow ip > "$OUT/dirty.txt"
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
