#!/bin/bash
# Brief 206 X13: simulate the funcsim netlists with glbl (GSR high for the first 100 ns). Sim-only (xsim, Basic).
# Usage: run_gsr.sh <net-dir> <work-dir>   -> prints the samples; record with > records/amd_gsr_sim.txt
set -eu
here=$(cd "$(dirname "$0")" && pwd); net=$1; w=$2; mkdir -p "$w"; cd "$w"
X=/opt/Xilinx/2026.1/Vivado/bin
G=/opt/Xilinx/2026.1/Vivado/data/verilog/src/glbl.v
for arm in x2 x4; do
  for initv in 0 1; do
    top=$( [ $arm = x2 ] && echo x2_sreset0 || echo x4_aclr )
    f=$net/xc7a35tcpg236-1_${arm}_${initv}.v
    echo "== $arm INITV=$initv ($top, xc7a35t funcsim netlist)"
    $X/xvlog -d DUT=$top "$f" "$G" "$here/tb_gsr.v" > xvlog_${arm}_${initv}.log
    $X/xelab -L unisims_ver -L secureip tb glbl -s s_${arm}_${initv} > xelab_${arm}_${initv}.log
    $X/xsim s_${arm}_${initv} -R 2>&1 | grep '^T[0-9]'
  done
done
