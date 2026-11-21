#!/bin/bash
# run_vivado_142.sh <slot text> <logfile> <jobs.tcl>...: wait for a heavy slot, run vivado_ooc.tcl on <jobs.tcl> (one thread, capped at 6G), release only our own lock.
# Usage note: the slot text must start with "142:"; @START@ and @END@ in it are replaced by the time taken and taken + 3 h. Poll every 120 s; give up after 12 h.
set -u
text=$1; log=$2; shift 2   # remaining arguments: job files, run one after the other in one slot
D=/home/brendan/Claude_sandbox/_handoff
HERE=$(cd "$(dirname "$0")" && pwd)
lock=""
for i in $(seq 1 360); do
  t=${text//@START@/$(date +%H:%M)}; t=${t//@END@/$(date -d "+3 hours" +%H:%M)}
  lock=$($D/take_heavy_slot.sh "$t") && break
  lock=""; sleep 120
done
[ -n "$lock" ] || { echo "no slot" > "$log"; exit 1; }
echo "slot $lock taken $(date)" > "$log"
set +u; source /opt/Xilinx/2026.1/Vivado/settings64.sh; set -u
for jobs in "$@"; do
  systemd-run --user --scope -p MemoryMax=6G vivado -mode batch -nojournal -nolog -source "$HERE/vivado_ooc.tcl" -tclargs "$jobs" >> "$log" 2>&1
  echo "vivado $jobs done $(date) rc=$?" >> "$log"
done
case "$(cat $lock)" in "142:"*) rm -f "$lock";; esac   # release only our own lock
