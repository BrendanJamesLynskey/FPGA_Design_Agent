#!/usr/bin/env bash
# usage: phasescan.sh : RAW benchmark, TXUSRCLK MMCM phase scan (edit CLKOUT0_PHASE of clk_wiz_1's MMCM in the generated sim source), one run per phase.
H=/home/brendan/Claude_sandbox/_handoff
P=/home/brendan/Claude_sandbox/_worktrees/186-sim/raw/Vivado_Project/project_1
X=$P/project_1.sim/sim_1/behav/xsim
F=$P/project_1.gen/sources_1/ip/clk_wiz_1/clk_wiz_1_clk_wiz.v
export PATH=/opt/Xilinx/2026.1/Vivado/bin:$PATH
while :; do
  L=$($H/take_heavy_slot.sh "186: xsim GTF raw latency phase scan (no Vivado synthesis), $(date +%H:%M), expected end $(date -d '+40 min' +%H:%M), peak 4G" 2>/dev/null) && break
  sleep 20
done
cp $F $F.orig
cd $X
echo "slot $L $(date)" > scan_slot.txt
for ph in -135 -90 -45 0 45 90 135; do
  sed "s/.CLKOUT0_PHASE        (-180.000)/.CLKOUT0_PHASE        ($ph.000)/" $F.orig > $F
  systemd-run --user --scope --quiet --unit=b186-scan-$(echo $ph | tr -d -) -p MemoryMax=6G nice -n 15 bash -c "
    bash compile.sh > scan_compile.log 2>&1 && bash elaborate.sh > scan_elab.log 2>&1
    xsim sim_top_behav -tclbatch run_all.tcl -log scan_phase_${ph}.log > /dev/null 2>&1"
  echo "TXPHASE=$ph deg: $(grep -E 'Latency calculation' scan_phase_${ph}.log | cut -c1-160)" >> scan_index.txt
done
cp $F.orig $F
echo "exit $? $(date)" >> scan_slot.txt
case "$(cat $L)" in "186:"*) rm -f $L;; esac
