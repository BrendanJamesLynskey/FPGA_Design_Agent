#!/usr/bin/env bash
# usage: macrun.sh <tag> <extra xsim args...> : MAC benchmark, no waveform recording, progress printed every 100 us of simulated time.
H=/home/brendan/Claude_sandbox/_handoff
X=/home/brendan/Claude_sandbox/_worktrees/186-sim/mac/Vivado_Project/project_1/project_1.sim/sim_1/behav/xsim
export PATH=/opt/Xilinx/2026.1/Vivado/bin:$PATH
tag=$1; shift
while :; do
  L=$($H/take_heavy_slot.sh "186: xsim GTF mac latency benchmark ($tag; no Vivado synthesis), $(date +%H:%M), expected end $(date -d '+45 min' +%H:%M), peak 4G" 2>/dev/null) && break
  sleep 20
done
cd $X
echo "slot $L $(date)" > mac_${tag}_slot.txt
cat > run_prog.tcl <<'T'
for {set i 0} {$i < 3000} {incr i} { run 100 us; puts "PROGRESS [current_time]" }
T
systemd-run --user --scope --quiet --unit=b186-mac-$tag -p MemoryMax=6G nice -n 15 bash -c "
  bash compile.sh > mac_compile.log 2>&1 && bash elaborate.sh > mac_elab.log 2>&1
  xsim gtfwizard_0_example_top_sim_behav -testplusarg REFOFF_PS=0 -testplusarg F300OFF_PS=0 $* -tclbatch run_prog.tcl -log mac_$tag.log > mac_${tag}.out 2>&1"
echo "exit $? $(date)" >> mac_${tag}_slot.txt
case "$(cat $L)" in "186:"*) rm -f $L;; esac
