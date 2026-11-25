#!/usr/bin/env bash
# uvm_build.sh: compile and elaborate the ITCH/OUCH UVM bench with Vivado 2026.1's xsim (brief 170).
#   scripts/uvm_build.sh <build dir> [rtl override dir]
# The design under test is `itch_unit` (rm_gp_itch/sim) with the real MACs and brief 110's blocks. A mutation run passes a directory holding mutated copies of some RTL files:
# a file found there replaces the original of the same name. Two snapshots are built: itch_uvm (the transmit MAC is paused one clock in 33, as the PCS gearbox does) and itch_uvm_np (never paused).
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"            # verif/uvm
VAR="$(cd "$HERE/../.." && pwd)"                     # rm_gp_itch
B96="$(cd "$VAR/.." && pwd)"                        # designs/b96_kr260_10g
B110="$(cd "$B96/.." && pwd)/b110_itch_ouch"
BUILD="$(mkdir -p "$1" && cd "$1" && pwd)"
OVR="${2:-}"
SETTINGS="${XSIM_SETTINGS:-$HOME/Xilinx/2026.1/Vivado/settings64.sh}"
[ -f "$SETTINGS" ] || SETTINGS=/opt/Xilinx/2026.1/Vivado/settings64.sh
set +eu; source "$SETTINGS" >/dev/null 2>&1; set -eu
pick() { local f="$1" n; n="$(basename "$f")"; if [ -n "$OVR" ] && [ -f "$OVR/$n" ]; then echo "$OVR/$n"; else echo "$f"; fi; }
FILES=""
for f in "$B96/rtl/b96_pkg.sv" "$B110/rtl/itch_pkg.sv" "$VAR/rtl/itch_pkg2.sv" "$B96/rtl/mac64_rx.sv" "$B96/rtl/mac64_tx.sv" \
         "$B110/rtl/mold_rx.sv" "$B110/rtl/itch_dec.sv" "$B110/rtl/book_core.sv" "$B110/rtl/risk_glue.sv" "$B110/rtl/ouch_enter.sv" \
         "$VAR/rtl/udp_strip.sv" "$VAR/rtl/order_seg.sv" "$VAR/rtl/itch_top.sv" "$VAR/rtl/itch_path.sv" "$VAR/rtl/tx_mux.sv" "$VAR/sim/itch_unit.sv"; do
  FILES="$FILES $(pick "$f")"
done
cd "$BUILD"
xvlog -sv -L uvm -i "$HERE" $FILES "$HERE/ref/itch_ref_pkg.sv" "$HERE/tb/itch_ifs.sv" "$HERE/itch_uvm_pkg.sv" "$HERE/sva/itch_sva.sv" "$HERE/tb/tb_itch_top.sv" > xvlog.log 2>&1 \
  || { grep -E "ERROR" xvlog.log | head -30; exit 1; }
xelab -L uvm tb_itch_top -s itch_uvm -debug off -timescale 1ns/1ps -mt 2 > xelab.log 2>&1 || { grep -E "ERROR" xelab.log | head -30; exit 1; }
if [ "${ITCH_BOTH:-1}" = 1 ]; then
  xelab -L uvm tb_itch_top -s itch_uvm_np -generic_top "PAUSE=0" -debug off -timescale 1ns/1ps -mt 2 > xelab_np.log 2>&1 || { grep -E "ERROR" xelab_np.log | head -30; exit 1; }
fi
echo "built $BUILD (override: ${OVR:-none})"
