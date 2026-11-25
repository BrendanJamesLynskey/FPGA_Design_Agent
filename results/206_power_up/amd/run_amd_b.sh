#!/bin/bash
# Brief 206 follow-up arms (amendment 2026-11-24): tcl/arms_b.tcl on both parts, under the caller's heavy slot.
# Usage: run_amd_b.sh <build-dir>   (records to results/206_power_up/records/amd_<part>_b.tsv)
set -eu
here=$(cd "$(dirname "$0")" && pwd)
b=${1:?build dir}; mkdir -p "$b/net"
V=/opt/Xilinx/2026.1/Vivado/bin/vivado
for part in xc7a35tcpg236-1 xck26-sfvc784-2LV-c; do
  (cd "$b" && systemd-run --user --scope --unit="fda206-amdb-${part%%-*}" -p MemoryMax=6G nice -n 15 "$V" -mode batch -notrace \
     -log "$b/amdb_$part.log" -journal "$b/amdb_$part.jou" -source "$here/tcl/arms_b.tcl" \
     -tclargs "$part" "$here/../records/amd_${part}_b.tsv" "$b/net")
done
