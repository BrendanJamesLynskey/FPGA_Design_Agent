#!/bin/bash
# chain.sh <design> <k1> <k2> ...: the runs of one design in turn, a record after each (stops at the STOP flag the cell sets at 89% weekly usage)
W=/home/brendan/Claude_sandbox/_worktrees/242-clock-groups; cd $W
D=$1; shift
for k in "$@"; do
  results/242_clock_groups/run_cell.sh $D $k > /dev/null 2>&1
  python3 pilots/242/record_one.py $D $k > /home/brendan/Claude_sandbox/_scratch_242/logs/rec_${D}_$k.txt 2>&1
  [ -e /home/brendan/Claude_sandbox/_scratch_242/STOP ] && break
done
