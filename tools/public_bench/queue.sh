#!/bin/bash
# queue.sh <ids file> <tag prefix>  -- run each problem id with run_one.sh, at most 2 at once; a problem whose log has an "exit" line is done
# and skipped; a launch that found no resources (WAIT_RESOURCES) or that died is retried on the next pass (up to 6 passes); stops on the STOP flag.
S=/home/brendan/Claude_sandbox/_scratch_215; R=/home/brendan/Claude_sandbox/_worktrees/215-public-benchmarks/tools/public_bench/run_one.sh
ids=$1; pre=$2
for pass in 1 2 3 4 5 6; do
  left=0
  while read -r id; do
    tag=${pre}_${id#cvdp_copilot_}; L=$S/logs/$tag.log
    grep -q "^20.* exit " $L 2>/dev/null && continue
    left=1
    while :; do
      [ -e $S/STOP ] && { echo "STOP flag: queue ends"; exit 3; }
      n=$(pgrep -fc "^/bin/bash /home/brendan/Claude_sandbox/_worktrees/215-public-benchmarks/tools/public_bench/run_one.sh"); [ "${n:-0}" -lt 2 ] && break
      sleep 20
    done
    mv -f $L $L.pass$((pass-1)) 2>/dev/null
    $R $id $tag >/dev/null 2>&1 &
    sleep 60
  done < $ids
  wait
  [ $left = 0 ] && break
  sleep 120
done
