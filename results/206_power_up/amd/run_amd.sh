#!/bin/bash
# Brief 206: run the AMD arms on both parts, in sequence, under the heavy slot the caller took.
# Usage: run_amd.sh <build-dir>   (records to results/206_power_up/records/amd_<part>.tsv, logs to <build-dir>)
set -eu
here=$(cd "$(dirname "$0")" && pwd)
b=${1:?build dir}; mkdir -p "$b/net"
V=/opt/Xilinx/2026.1/Vivado/bin/vivado
for part in xc7a35tcpg236-1 xck26-sfvc784-2LV-c; do
  (cd "$b" && systemd-run --user --scope --unit="fda206-amd-${part%%-*}" -p MemoryMax=5G nice -n 15 "$V" -mode batch -notrace \
     -log "$b/amd_$part.log" -journal "$b/amd_$part.jou" -source "$here/tcl/arms.tcl" \
     -tclargs "$part" "$here/../records/amd_$part.tsv" "$b/net")
done
