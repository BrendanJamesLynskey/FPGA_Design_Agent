#!/usr/bin/env bash
# usage: runsim.sh <raw|mac>  : take a "186:" heavy slot, run the Vivado project setup + xsim, release the slot.
H=/home/brendan/Claude_sandbox/_handoff
D=/home/brendan/Claude_sandbox/_worktrees/186-sim/$1/Vivado_Project
cd $D || exit 1
while :; do
  L=$($H/take_heavy_slot.sh "186: Vivado IP generation + xsim, GTF $1 latency benchmark simulation (no synthesis), $(date +%H:%M), expected end $(date -d '+60 min' +%H:%M), peak 6G" 2>/dev/null) && break
  sleep 20
done
echo "slot $L $(date)" > slot.txt
systemd-run --user --scope --quiet --unit=b186-$1sim -p MemoryMax=6G nice -n 15 \
  /opt/Xilinx/2026.1/Vivado/bin/vivado -mode batch -nojournal -log vivado_$1.log -source run_$1.tcl > run_$1.out 2>&1
echo "exit $? $(date)" >> slot.txt
case "$(cat $L)" in "186:"*) rm -f $L;; esac
