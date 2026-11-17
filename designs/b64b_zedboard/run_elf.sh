#!/bin/bash
# run_elf.sh <elf> <log out> [timeout s]   (needs ZB_SERIAL in the environment and a running hw_server; see tcl/run_elf.tcl)
set -e
D=$(cd "$(dirname "$0")" && pwd)
source /opt/Xilinx/2026.1/Vitis/settings64.sh >/dev/null 2>&1
: "${XSA_DIR:?set XSA_DIR to the unzipped XSA directory}" "${BIT:=zb_hwsw.bit}"
timeout $((${3:-300}+120)) xsdb "$D/tcl/run_elf.tcl" "$XSA_DIR" "$BIT" "$1" "$2" "${3:-300}"
