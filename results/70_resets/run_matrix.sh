#!/bin/bash
# Brief 70 Part 1 driver: both parts, in sequence, under one heavy slot taken by the caller (take_heavy_slot.sh).
# Usage: run_matrix.sh <scratch-dir>      (records go to results/70_resets/records/<part>.tsv; one run each)
set -eu
here=$(cd "$(dirname "$0")" && pwd)
scratch=${1:?scratch dir}
V=/opt/Xilinx/2026.1/Vivado/bin/vivado
for part in xc7a100tcsg324-1 xck26-sfvc784-2LV-c; do
  rm -f "$here/records/$part.tsv"
  (cd "$scratch" && systemd-run --user --scope -p MemoryMax=6G nice -n 15 "$V" -mode batch -notrace -log "$scratch/$part.log" -journal "$scratch/$part.jou" \
     -source "$here/tcl/matrix.tcl" -tclargs "$part" "$here/records/$part.tsv")
done
