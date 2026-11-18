#!/usr/bin/env bash
# produce_crc_netlist.sh: how ext/crc32_d16.edf was made, as a supplier would: Yosys synth_xilinx (UltraScale+ family) of the
# supplier's RTL (ext/reference/crc32_d16.sv), written as EDIF for Vivado (read_edif) and as a Verilog netlist for simulation.
# This runs OUTSIDE the project build (Yosys, not Vivado; no agent). The project only receives the files and checks them
# (flow/managed_import.py). Needs the OSS CAD Suite (set FDA_OSS_CAD to its folder).
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
[ -n "${FDA_OSS_CAD:-}" ] && export PATH="$FDA_OSS_CAD/bin:$PATH"
cd "$HERE/ext"
yosys -q -p "read_verilog -sv reference/crc32_d16.sv; synth_xilinx -family xcup -top crc32_d16 -flatten; \
  write_edif -pvector bra crc32_d16.edf; write_verilog -noattr crc32_d16_netlist.v"
{ yosys -V; sha256sum reference/crc32_d16.sv crc32_d16.edf crc32_d16_netlist.v; } > PRODUCED.txt
echo "wrote ext/crc32_d16.edf, ext/crc32_d16_netlist.v, ext/PRODUCED.txt"
