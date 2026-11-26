#!/bin/bash
# Brief 169, the D question: does a routing-delay difference between the go-pulse crossing and the other crossings make D depend on the clock phase, as the board's D-against-E pattern suggests?
# Takes the `base` build directory of core_sim.sh (parameters off = lat_all3_bypass), replaces the go-pulse crossing by a behavioural copy with SK ns of delay between its toggle flop and its first synchroniser flop (zero in the normal simulations) and runs 16 phases of the receive clock. usage: SK=1.5 results/b169/skew_sim.sh   (needs results/b169/core_sim.sh base to have run once: build/core_sim169/x_base)
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; H=$ROOT/results/b169; SK="${SK:-1.5}"; NORD="${NORD:-8}"
WORK="$ROOT/build/core_sim169"; X="$WORK/x_skew$SK"; rm -rf "$X"; cp -r "$WORK/x_base" "$X"; rm -rf "$X"/r_*
set +u; source /opt/Xilinx/2026.1/Vivado/settings64.sh >/dev/null 2>&1; set -u
python3 - "$X/b96_core.sv" "$SK" <<'PY'
import re, sys
p, sk = sys.argv[1], sys.argv[2]
t = open(p).read()
m = re.search(r"        xpm_cdc_pulse #\(\.DEST_SYNC_FF\(2\)[^\n]*u_p_go[^\n]*\n", t)
assert m
# a behavioural copy of the go-pulse crossing (toggle flop, two synchroniser flops, XOR edge detect, no output register = DEST_SYNC_FF 2, REG_OUTPUT 0) with a delay of SK ns between the toggle flop and the first
# synchroniser flop: the routing delay each real crossing has and the zero-delay simulation does not. SK = 0 must reproduce the XPM model's numbers (checked by the script's first run).
rep = ("        logic go_tg, go_tg_d, go_f1, go_f2, go_f3;\n        initial begin go_tg = 1'b0; go_f1 = 1'b0; go_f2 = 1'b0; go_f3 = 1'b0; end\n"
       "        always @(posedge rxusr2) if (r_fire) go_tg <= ~go_tg;\n        assign #" + sk + " go_tg_d = go_tg;\n"
       "        always @(posedge txusr2) begin go_f1 <= go_tg_d; go_f2 <= go_f1; go_f3 <= go_f2; end\n        assign go_t = go_f2 ^ go_f3;\n")
t = t.replace(m.group(0), rep)
open(p, "w").write("`timescale 1ns/1ps\n" + t)
PY
sed -i "s/parameter int NORD = [0-9]*/parameter int NORD = $NORD/" "$X/tb_lat_core169.sv"
OUT="$H/skew/sk$SK"; mkdir -p "$OUT"
SRCS="b96_pkg.sv pcs_tx.sv pcs_rx.sv mac64_tx.sv mac64_rx.sv hs_vec.sv frame_src.sv trade64.sv rate_match.sv rate_match_gp.sv tx_path.sv rx_path.sv rx_path_legacy.sv gt_bp_gate.sv gt_bp_ctl.sv b96_core.sv"
for ph in ${PHASES:-0 400 800 1200 1600 2000 2400 2800 3200 3600 4000 4400 4800 5200 5600 6000}; do
  w="$X/r_$ph"; mkdir -p "$w"
  ( cd "$w" && xvlog -sv -L xpm -d RXPH=$(python3 -c "print($ph/1000.0)") -d BP_CLKS=100 -d HANG_TX=0 -d HANG_RX=0 -d BPTO=4833984 -d BPRTY=3 $(for fl in $SRCS; do echo ../$fl; done) ../gth_wiz_model.sv ../tb_lat_core169.sv "$XILINX_VIVADO/data/verilog/src/glbl.v" > xvlog.log 2>&1 \
    && xelab -L xpm -L unisims_ver -debug off -generic_top "RATE_MATCH=0" -generic_top "RM_OWN=0" -generic_top "RM_DIRECT=0" -generic_top "GO_REG=0" -generic_top "EARLY_MAC=0" -generic_top "FAST_PRE=0" tb_lat_core126 work.glbl -s s > xelab.log 2>&1 && xsim s -R > xsim.log 2>&1 )
  grep -E "^(ORD|RET|DONE|SAFETY)" "$w/xsim.log" > "$OUT/ord_$ph.log"; echo "sk $SK phase $ph: $(grep -c ^ORD "$OUT/ord_$ph.log") orders"
done
python3 "$H/reduce169.py" "$OUT" "$OUT.json" > "$OUT/reduction.txt"; cat "$OUT/reduction.txt"
