#!/usr/bin/env bash
# lint.sh: Verilator --lint-only -Wall on every ip_lib networking entry (brief 40). Waived classes, with reasons:
#   UNUSEDSIGNAL  the tables take a 512-bit command word and each reads only its fields; header words are read in part
#   BLKSEQ        blocking temporaries inside always_ff (declared in the block) are deliberate
#   PINCONNECTEMPTY  unused outputs of reused library entries are left open on purpose
set -euo pipefail
cd "$(dirname "$0")/../../ip_lib"
verilator --version
W="-Wall -Wno-UNUSEDSIGNAL -Wno-BLKSEQ -Wno-PINCONNECTEMPTY"
for t in eth_mac_rmii pkt_parser match_exact match_lpm match_ternary axil_table_ctrl pkt_rewrite pkt_queue_sched; do
  echo "lint: $t"; verilator --lint-only $W --top-module "$t" "$t"/rtl/*.sv
done
echo "lint: l2_switch"; verilator --lint-only $W --top-module l2_switch l2_switch/rtl/*.sv match_exact/rtl/*.sv pkt_queue_sched/rtl/*.sv
echo "lint: eth_mac_rgmii (with the XPM simulation models, their own warnings waived)"
verilator --lint-only $W --top-module eth_mac_rgmii ../flow/net/xpm_models.vlt ../flow/cdc_models/cdc_inj_pkg.sv \
  ../flow/cdc_models/xpm_cdc_models.sv eth_mac_rmii/rtl/eth_crc32.sv eth_mac_rgmii/rtl/*.sv
echo "lint: clean"
