#!/usr/bin/env bash
# report_cdc for every built variant and the 96 baseline, in one heavy slot. results/b97/cdc_all.sh [wait minutes]
set -uo pipefail
cd /home/brendan/Claude_sandbox/_worktrees/97-latency
H=/home/brendan/Claude_sandbox/_handoff; VIV=/opt/Xilinx/2026.1/Vivado/bin/vivado
TEXT="97: Vivado read-only report_cdc on routed checkpoints peak 3G, $(date +%H:%M), expected end $(date -d '+30 min' +%H:%M)"
n=0; while true; do out="$("$H/take_heavy_slot.sh" --env "$TEXT" 2>/dev/null)" && [ -n "$out" ] && { eval "$out"; break; }; n=$((n+1)); [ "$n" -ge "${1:-240}" ] && exit 1; sleep 60;   if [ $v != baseline ]; then python3 - "$v" <<'PY'
import sys
from pathlib import Path
from flow.latency import netlist
v = sys.argv[1]
d = Path("designs/b96_kr260_10g")
r = netlist.run(d, d / f"lat_{v}" / "build" / "base" / "post_route.dcp", Path("results/b97/builds") / v / "slack.json")
print(v, {k: x["setup_slack_ns"] for k, x in r["stages"].items()})
PY
  fi
done
trap 'case "$(cat "$HEAVY_LOCK" 2>/dev/null)" in "97:"*) rm -f "$HEAVY_LOCK";; esac' EXIT
mkdir -p results/b97/cdc
for v in baseline hand_ref agent_both all3 agent_cdc; do
  if [ $v = baseline ]; then D=/home/brendan/Claude_sandbox/_worktrees/96-kr260-10g/designs/b96_kr260_10g/build/base/post_route.dcp; else D=designs/b96_kr260_10g/lat_$v/build/base/post_route.dcp; fi
  [ -f $D ] || { echo "skip $v"; continue; }
  ( cd build/latency && systemd-run --user --scope -q -p MemoryMax=4G nice -n 15 $VIV -mode batch -nojournal -nolog -source /home/brendan/Claude_sandbox/_worktrees/97-latency/results/b97/cdc_report.tcl -tclargs $(realpath ../../$D 2>/dev/null || echo $D) /home/brendan/Claude_sandbox/_worktrees/97-latency/results/b97/cdc/$v ) 2>&1 | tail -2
done
