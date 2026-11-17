#!/usr/bin/env bash
# The read-only Vivado work of brief 97, in one heavy slot: (1) the per-stage post-route slack of the 96 baseline checkpoint, (2) Vivado 2026.1's own
# help and property tables for the phase 2 plan, (3) the GT Wizard's buffer-bypass properties and the ports the core then adds. No implementation, no board.
#   results/b97/vivado_probes.sh [wait minutes, default 240]
set -uo pipefail
WAIT="${1:-240}"
ROOT=/home/brendan/Claude_sandbox/_worktrees/97-latency
ROOT96=/home/brendan/Claude_sandbox/_worktrees/96-kr260-10g
H=/home/brendan/Claude_sandbox/_handoff
VIV=/opt/Xilinx/2026.1/Vivado/bin/vivado
cd "$ROOT"
TEXT="97: Vivado read-only probes (checkpoint read, help, IP generate; no implementation) peak 3G, $(date +%H:%M), expected end $(date -d '+25 min' +%H:%M)"
n=0
while true; do
  out="$("$H/take_heavy_slot.sh" --env "$TEXT" 2>/dev/null)" && [ -n "$out" ] && { eval "$out"; break; }
  n=$((n+1)); [ "$n" -ge "$WAIT" ] && { echo "no heavy slot within $WAIT minutes"; exit 1; }
  sleep 60
done
release() { case "$(cat "$HEAVY_LOCK" 2>/dev/null)" in "97:"*) rm -f "$HEAVY_LOCK";; esac; }
trap release EXIT
echo "slot $HEAVY_LOCK taken"
DCP="$ROOT96/designs/b96_kr260_10g/build/base/post_route.dcp"
mkdir -p build/latency
python3 - "$DCP" <<'PY'
import sys
from pathlib import Path
from flow.latency import netlist
d = Path("designs/b96_kr260_10g")
r = netlist.run(d, Path(sys.argv[1]), Path("results/b96/latency_slack.json"))
print({k: (v["cells"], v["clock"], v["setup_slack_ns"]) for k, v in r["stages"].items()})
PY
( cd build/latency && systemd-run --user --scope -q -p MemoryMax=4G nice -n 15 "$VIV" -mode batch -nojournal -nolog -source "$ROOT/results/b97/phase2_probe.tcl" -tclargs "$DCP" "$ROOT/results/b97/phase2_probe.txt" ) 2>&1 | tail -5
( cd build/latency && systemd-run --user --scope -q -p MemoryMax=4G nice -n 15 "$VIV" -mode batch -nojournal -nolog -source "$ROOT/results/b97/gt_bypass_probe.tcl" -tclargs "$ROOT/results/b97/gt_bypass_probe.txt" ) 2>&1 | tail -5
ls -la results/b97/*.txt results/b96/latency_slack.json
