#!/usr/bin/env bash
# uvm_build.sh: compile and elaborate the b96 PCS and MAC UVM bench with Vivado 2026.1's xsim (brief 112).
#   scripts/uvm_build.sh <build dir> [rtl dir]      rtl dir defaults to designs/b96_kr260_10g/rtl; a mutant run passes a mutated copy
# Needs no GT model (the channel replaces the GTH). Writes <build dir>/xvlog.log, xelab.log and the snapshot "pcs_uvm".
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"            # verif/uvm
DESIGN="$(cd "$HERE/../.." && pwd)"                 # designs/b96_kr260_10g
BUILD="$(mkdir -p "$1" && cd "$1" && pwd)"
RTL="${2:-$DESIGN/rtl}"
SETTINGS="${XSIM_SETTINGS:-$HOME/Xilinx/2026.1/Vivado/settings64.sh}"
# shellcheck disable=SC1090
[ -f "$SETTINGS" ] || SETTINGS=/opt/Xilinx/2026.1/Vivado/settings64.sh
set +eu; source "$SETTINGS" >/dev/null 2>&1; set -eu
cd "$BUILD"
RTLF="$RTL/b96_pkg.sv $RTL/pcs_tx.sv $RTL/pcs_rx.sv $RTL/mac64_tx.sv $RTL/mac64_rx.sv"
xvlog -sv -L uvm -i "$HERE" $RTLF "$HERE/ref/pcs_ref_pkg.sv" "$HERE/tb/pcs_mac_ifs.sv" "$HERE/tb/line_channel.sv" \
      "$HERE/pcs_mac_uvm_pkg.sv" "$HERE/sva/pcs_mac_sva.sv" "$HERE/tb/tb_uvm_top.sv" > xvlog.log 2>&1 || { grep -E "ERROR" xvlog.log | head -30; exit 1; }
xelab -L uvm tb_uvm_top -s pcs_uvm -debug off -timescale 1ns/1ps -mt 2 > xelab.log 2>&1 || { grep -E "ERROR" xelab.log | head -30; exit 1; }
echo "built $BUILD (rtl: $RTL)"
