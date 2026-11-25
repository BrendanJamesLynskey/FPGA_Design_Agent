#!/usr/bin/env bash
# 186 (rev 2: normal licence environment; the no-licence variant does not start on 2026.1, see licence_check_nolicence.log): wait for a heavy slot, run brief 33's licence check for xcvu2p, release the slot.
H=/home/brendan/Claude_sandbox/_handoff
W=/home/brendan/Claude_sandbox/_worktrees/186-ul3524
OUT=$W/results/186_ul3524
while :; do
  L=$($H/take_heavy_slot.sh "186: Vivado impl licence check xcvu2p tiny counter, $(date +%H:%M), expected end $(date -d '+20 min' +%H:%M), peak 2G" 2>/dev/null) && break
  sleep 20
done
echo "slot $L at $(date)" > $OUT/licence_run.txt
cd $W/results/33_vivado_speed_2026_1 2>/dev/null || cd $W/results/186_ul3524
EMPTY=$(mktemp -d); cd $EMPTY
SRC=$W/results/33_vivado_speed_2026_1
cd $EMPTY; env LC_PARTS="xcvu2p-fsvj2104-3-e" \
  systemd-run --user --scope --quiet --unit=b186-licence-check -p MemoryMax=4G nice -n 15 \
  /opt/Xilinx/2026.1/Vivado/bin/vivado -mode batch -nojournal -nolog -source $SRC/licence_check.tcl > $OUT/licence_check.log 2>&1
echo "exit $?" >> $OUT/licence_run.txt
date >> $OUT/licence_run.txt
cd /; rm -rf $EMPTY
case "$(cat $L)" in "186:"*) rm -f $L;; esac
