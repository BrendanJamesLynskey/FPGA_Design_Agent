#!/bin/bash
# Brief 206: the follow-up arms again without X7 (tcl/arms_scan.tcl), after the init-scan fix; records amd_<part>_scan.tsv.
# Usage: run_amd_scan.sh <build-dir>   (init scans overwrite <build-dir>/net/*_init_scan.tsv; copy them to records/init_scan)
set -eu
here=$(cd "$(dirname "$0")" && pwd)
b=${1:?build dir}; mkdir -p "$b/net"
V=/opt/Xilinx/2026.1/Vivado/bin/vivado
for part in xc7a35tcpg236-1 xck26-sfvc784-2LV-c; do
  (cd "$b" && systemd-run --user --scope --unit="fda206-amdscan-${part%%-*}" -p MemoryMax=6G nice -n 15 "$V" -mode batch -notrace \
     -log "$b/amdscan_$part.log" -journal "$b/amdscan_$part.jou" -source "$here/tcl/arms_scan.tcl" \
     -tclargs "$part" "$here/../records/amd_${part}_scan.tsv" "$b/net")
done
