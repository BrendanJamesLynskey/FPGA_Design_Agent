#!/usr/bin/env bash
# Build one latency variant (designs/b96_kr260_10g/lat_<variant>) through the flow, under the heavy-slot rule, then record the post-route digest and the
# per-stage slack (flow/latency/netlist_slack.tcl) into results/b97/builds/<variant>/. Waits for a slot (retries every 60 s, up to <wait minutes>).
#   results/b97/build_variant.sh <variant> [peak GB, default 6] [wait minutes, default 240]
set -uo pipefail
V="${1:?variant name}"; PEAK="${2:-6}"; WAIT="${3:-240}"
ROOT=/home/brendan/Claude_sandbox/_worktrees/97-latency
H=/home/brendan/Claude_sandbox/_handoff
cd "$ROOT"
TEXT="97: Vivado impl $V peak ${PEAK}G, $(date +%H:%M), expected end $(date -d '+40 min' +%H:%M)"
n=0
while true; do
  out="$("$H/take_heavy_slot.sh" --env "$TEXT" 2>/dev/null)" && [ -n "$out" ] && { eval "$out"; break; }
  n=$((n+1)); [ "$n" -ge "$WAIT" ] && { echo "no heavy slot within $WAIT minutes"; exit 1; }
  sleep 60
done
release() { case "$(cat "$HEAVY_LOCK" 2>/dev/null)" in "97:"*) rm -f "$HEAVY_LOCK";; esac; }
trap release EXIT
export FDA_VIVADO_THREADS=1   # 2 threads hit the 6 GiB cap and the kernel OOM-killed all four first attempts (swap nearly full)
echo "slot $HEAVY_LOCK taken: $(cat "$HEAVY_LOCK"); threads $FDA_VIVADO_THREADS"
OUT="$ROOT/results/b97/builds/$V"; mkdir -p "$OUT"
export FDA_VIVADO_MAX=3
flow/run_vivado.sh "designs/b96_kr260_10g/lat_$V" base 2>&1 | tail -40 | tee "$OUT/run_vivado.log"
B="designs/b96_kr260_10g/lat_$V/build/base"
[ -f "$B/post_route.dcp" ] || { echo "no post_route.dcp: build failed"; exit 2; }
python3 - "$B" "$OUT" <<'PY'
import json, sys
from pathlib import Path
from flow.digest.build import digest_build
b, out = Path(sys.argv[1]), Path(sys.argv[2])
d = digest_build(b)
keep = {k: d.get(k) for k in ("timing", "utilization", "power", "gates", "drc", "methodology")}
(out / "digest.json").write_text(json.dumps(keep, indent=1, default=str) + "\n")
print(json.dumps({k: keep[k] for k in ("timing",)}, default=str)[:600])
PY
cp "$B/run.json" "$OUT/run.json" 2>/dev/null || true
python3 - "$V" <<'PY'
import sys
from pathlib import Path
from flow.latency import netlist
d = Path("designs/b96_kr260_10g")
r = netlist.run(d, d / f"lat_{sys.argv[1]}" / "build" / "base" / "post_route.dcp", Path("results/b97/builds") / sys.argv[1] / "slack.json")
print({k: v["setup_slack_ns"] for k, v in r["stages"].items()})
PY
