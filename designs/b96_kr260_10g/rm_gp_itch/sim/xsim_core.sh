#!/bin/bash
# Brief 127: the whole core of build rm_gp_itch in xsim 2026.1 with AMD's real XPM macros (sim/tb_itch_core.sv + the GT stand-in), running one host script.
# usage: xsim_core.sh <script file> <work dir> [phase ps the receive clock lags the transmit clock, default 0] [RM_OWN 0|1, default 1]
# Writes <work dir>/xsim.log (the monitors' lines and the script's reads). Simulation only: no heavy slot needed while the load is under 6 and more than 12 GB is free (house rules).
# xsim refuses a variable driven by an `initial` block and an always_ff, and the real XPM synchronisers start X with INIT_SYNC_FF = 0 (the toggling handshakes then never settle): the RTL is
# compiled from a copy with always_ff turned into plain `always` (same behaviour) and INIT_SYNC_FF 0 -> 1 (UG974: the simulation initial value only), as results/b96e/core_lat_sim.sh does.
set -uo pipefail
SCRIPT="$(readlink -f "${1:?script}")"; WORK="${2:?work dir}"; PH="${3:-0}"; OWN="${4:-1}"
HERE="$(cd "$(dirname "$0")" && pwd)"; D="$(cd "$HERE/.." && pwd)"; B96="$(cd "$D/.." && pwd)"; B110="$(cd "$B96/../b110_itch_ouch" && pwd)"
mkdir -p "$WORK"; cd "$WORK"
set +u; source /opt/Xilinx/2026.1/Vivado/settings64.sh >/dev/null 2>&1; set -u
mkdir -p rtl_x
SRC=("$B96/rtl/b96_pkg.sv" "$B110/rtl/itch_pkg.sv" "$D/rtl/itch_pkg2.sv" "$B96/rtl/pcs_tx.sv" "$B96/rtl/pcs_rx.sv" "$B96/rtl/mac64_tx.sv" "$B96/rtl/mac64_rx.sv" "$B96/rtl/hs_vec.sv"
     "$B96/rtl/frame_src.sv" "$B96/rtl/trade64.sv" "$B96/rtl/rate_match.sv" "$B96/rtl/rate_match_gp.sv"
     "$B110/rtl/mold_rx.sv" "$B110/rtl/itch_dec.sv" "$B110/rtl/book_core.sv" "$B110/rtl/risk_glue.sv" "$B110/rtl/ouch_enter.sv"
     "$D/rtl/udp_strip.sv" "$D/rtl/order_seg.sv" "$D/rtl/itch_top.sv" "$D/rtl/itch_path.sv" "$D/rtl/tx_mux.sv" "$D/rtl/rx_path.sv" "$D/rtl/tx_path.sv" "$D/rtl/b96_core.sv"
     "$B96/sim/gth_wiz_model96e.sv" "$D/sim/tb_itch_core.sv")
OUT=()
for f in "${SRC[@]}"; do b=$(basename "$f"); sed -e 's/always_ff @(/always @(/' -e 's/INIT_SYNC_FF(0)/INIT_SYNC_FF(1)/' "$f" > "rtl_x/$b"; OUT+=("rtl_x/$b"); done
NS=$(python3 -c "print($PH/1000.0)")
xvlog -sv -L xpm -d RXPH=$NS "${OUT[@]}" "$XILINX_VIVADO/data/verilog/src/glbl.v" > xvlog.log 2>&1 || { echo "xvlog failed"; tail -20 xvlog.log; exit 2; }
xelab -L xpm -L unisims_ver -debug off -generic_top "RM_OWN=$OWN" tb_itch_core work.glbl -s s > xelab.log 2>&1 || { echo "xelab failed"; tail -20 xelab.log; exit 3; }
xsim s -R -testplusarg "script=$SCRIPT" > xsim.log 2>&1
tail -3 xsim.log
