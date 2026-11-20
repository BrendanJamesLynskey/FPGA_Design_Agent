#!/usr/bin/env bash
# Brief 96F1: the buffer-bypass start-up sequence in xsim 2026.1 with AMD's own controllers (the generated sources of ip/amd_ip_bypass.tcl; not committed) and the stand-in transceiver of
# designs/b96_kr260_10g/rm_gp_bypass/sim/tb_bp_seq.sv. Simulation only (the IP generate is a short Vivado batch run: take a heavy slot for it as for any Vivado job).
#   results/b96f1/bypass_seq/run.sh [work dir, default build/bypass_seq]
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"; D=designs/b96_kr260_10g
WORK="${1:-$ROOT/build/bypass_seq}"; mkdir -p "$WORK"; cd "$WORK"
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
H="$WORK/ip/gth_wiz/hdl"
xvlog -sv "$H/gtwizard_ultrascale_v1_7_bit_sync.v" "$H/gtwizard_ultrascale_v1_7_reset_inv_sync.v" "$H/gtwizard_ultrascale_v1_7_gtwiz_buffbypass_tx.v" "$H/gtwizard_ultrascale_v1_7_gtwiz_buffbypass_rx.v" \
      "$ROOT/$D/rm_gp_bypass/rtl/gt_bp_gate.sv" "$ROOT/$D/rm_gp_bypass/sim/tb_bp_seq.sv" > xvlog.log 2>&1 || { tail -20 xvlog.log; exit 1; }
xelab -debug off tb_bp_seq -s s > xelab.log 2>&1 || { tail -20 xelab.log; exit 1; }
xsim s -R > xsim.log 2>&1
grep -E "^(ok|FAIL|INFO|PASS)" xsim.log
