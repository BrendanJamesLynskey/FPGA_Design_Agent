#!/usr/bin/env bash
# Brief 96F1b: the reset drive and the alignment timeout/retry of gt_bp_ctl in xsim 2026.1 with AMD's own buffer-bypass controllers (the generated sources of ip/amd_ip_bypass.tcl; not committed)
# against the stand-in transceiver of designs/b96_kr260_10g/rm_gp_bypass/sim/tb_bp_ctl.sv, plus the existing 96F1 sequence bench (tb_bp_seq.sv, 28 checks) run unchanged against the new gate.
# Simulation only (the IP generate is a short Vivado batch run: take a heavy slot for it as for any Vivado job; copy $WORK/ip from an earlier generate to skip it).
#   results/b96f1b/bypass_ctl/run.sh [work dir, default build/bypass_ctl] [full]     "full" runs only the real-value case (30 ms = 4,833,984 clocks), a few minutes
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"; D=designs/b96_kr260_10g
WORK="${1:-$ROOT/build/bypass_ctl}"; FULL="${2:-}"; mkdir -p "$WORK"; cd "$WORK"
set +u; source /opt/Xilinx/2026.1/Vivado/settings64.sh >/dev/null 2>&1; set -u
if [ ! -d "$WORK/ip/gth_wiz/hdl" ]; then
  cat > gen.tcl <<TCL
set part xck26-sfvc784-2LV-c
set out $WORK
create_project -in_memory -part \$part
source $ROOT/$D/ip/amd_ip_bypass.tcl
TCL
  systemd-run --user --scope -p MemoryMax=4G nice -n 15 vivado -mode batch -nojournal -log gen.log -source gen.tcl > /dev/null 2>&1 || { echo "IP generate failed: see $WORK/gen.log"; exit 1; }
fi
H="$WORK/ip/gth_wiz/hdl"; V="$ROOT/$D/rm_gp_bypass"
# xsim needs always_ff -> always and INIT_SYNC_FF 0 -> 1 in the copies (as results/b96f1/core_sim.sh; the rtl files themselves are not touched)
mkdir -p rtl_x; for f in "$V"/rtl/gt_bp_gate.sv "$V"/rtl/gt_bp_ctl.sv; do sed -e 's/always_ff @(/always @(/' -e 's/INIT_SYNC_FF(0)/INIT_SYNC_FF(1)/' "$f" > rtl_x/$(basename "$f"); done
DEFS=""; [ "$FULL" = full ] && DEFS="-d FULL"
GEN="$H/gtwizard_ultrascale_v1_7_bit_sync.v $H/gtwizard_ultrascale_v1_7_reset_inv_sync.v $H/gtwizard_ultrascale_v1_7_gtwiz_buffbypass_tx.v $H/gtwizard_ultrascale_v1_7_gtwiz_buffbypass_rx.v"
run() {   # run <top> <sv files...>
  top="$1"; shift; mkdir -p "$top$FULL"; ( cd "$top$FULL" && xvlog -sv -L xpm $DEFS $GEN "$@" "$XILINX_VIVADO/data/verilog/src/glbl.v" > xvlog.log 2>&1 && xelab -L xpm -L unisims_ver -debug off "$top" work.glbl -s s > xelab.log 2>&1 && xsim s -R > xsim.log 2>&1 ) \
    || { echo "$top: build or run failed"; tail -20 "$top$FULL"/xvlog.log "$top$FULL"/xelab.log 2>/dev/null; return 1; }
  grep -E "^(ok|FAIL|INFO|PASS)" "$top$FULL/xsim.log"
}
if [ "$FULL" = full ]; then
  run tb_bp_ctl "$WORK/rtl_x/gt_bp_gate.sv" "$WORK/rtl_x/gt_bp_ctl.sv" "$V/sim/tb_bp_ctl.sv"
else
  echo "== tb_bp_ctl (scaled timeouts: TX 6000, RX 26000 clocks)"; run tb_bp_ctl "$WORK/rtl_x/gt_bp_gate.sv" "$WORK/rtl_x/gt_bp_ctl.sv" "$V/sim/tb_bp_ctl.sv"
  echo "== tb_bp_seq (96F1's 28 checks, unchanged bench, new gate)"; run tb_bp_seq "$WORK/rtl_x/gt_bp_gate.sv" "$V/sim/tb_bp_seq.sv"
fi
