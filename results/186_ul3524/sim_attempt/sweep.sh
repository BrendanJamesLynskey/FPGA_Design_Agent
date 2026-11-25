#!/usr/bin/env bash
# usage: sweep.sh <raw|mac> : take a "186:" slot, recompile edited sim files, run the phase/reset sweep, release the slot.
H=/home/brendan/Claude_sandbox/_handoff
K=$1
X=/home/brendan/Claude_sandbox/_worktrees/186-sim/$K/Vivado_Project/project_1/project_1.sim/sim_1/behav/xsim
export PATH=/opt/Xilinx/2026.1/Vivado/bin:$PATH
while :; do
  L=$($H/take_heavy_slot.sh "186: xsim GTF $K latency benchmark sweep (no Vivado synthesis), $(date +%H:%M), expected end $(date -d '+75 min' +%H:%M), peak 4G" 2>/dev/null) && break
  sleep 20
done
cd $X
echo "slot $L $(date)" > sweep_slot.txt
echo 'run all' > run_all.tcl; echo 'quit' >> run_all.tcl
systemd-run --user --scope --quiet --unit=b186-$K-sweep -p MemoryMax=6G nice -n 15 bash -c '
  bash compile.sh > sweep_compile.log 2>&1 && bash elaborate.sh > sweep_elab.log 2>&1
  i=0
  for ro in 0 800 1600 2400 3200 4000 4800 5600; do
    for fo in 0 1111; do
      for rd in 1000; do
        i=$((i+1))
        xsim sim_top_behav -testplusarg REFOFF_PS=$ro -testplusarg F300OFF_PS=$fo -testplusarg RSTDLY=$((rd+i*7)) -tclbatch run_all.tcl -log sweep_run_${i}.log > /dev/null 2>&1
        echo "run $i REFOFF_PS=$ro F300OFF_PS=$fo RSTDLY=$((rd+i*7)): $(grep -E "Latency calculation" sweep_run_${i}.log | cut -c1-160)" >> sweep_index.txt
      done
    done
  done'
echo "exit $? $(date)" >> sweep_slot.txt
case "$(cat $L)" in "186:"*) rm -f $L;; esac
