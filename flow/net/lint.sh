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
verilator --lint-only $W -Wno-WIDTHEXPAND --top-module eth_mac_rgmii ../flow/net/xpm_models.vlt ../flow/cdc_models/cdc_inj_pkg.sv \
  ../flow/cdc_models/xpm_cdc_models.sv eth_mac_rmii/rtl/eth_crc32.sv eth_mac_rgmii/rtl/*.sv
echo "lint: brief 63D entries (WIDTHEXPAND waived: untyped string parameters such as RAM compared with longer literals)"
for t in mdio_master arp_responder icmp_echo ipv4_udp_rx ipv4_udp_tx igmp_join; do
  echo "lint: $t"; verilator --lint-only $W -Wno-WIDTHEXPAND --top-module "$t" "$t"/rtl/*.sv
done
echo "lint: eth_mac_rgmii 0.2 with every feature on"
verilator --lint-only $W -Wno-WIDTHEXPAND --top-module eth_mac_rgmii -GCUT_THROUGH=0 -GFILTER=1 -GVLAN=2 -GPAUSE=1 \
  -GSTATS=1 ../flow/net/xpm_models.vlt ../flow/cdc_models/cdc_inj_pkg.sv ../flow/cdc_models/xpm_cdc_models.sv \
  eth_mac_rmii/rtl/eth_crc32.sv eth_mac_rgmii/rtl/*.sv
echo "lint: brief 151 partitioning entries (DECLFILENAME and UNUSEDPARAM also waived: one file holds several slice modules; sideband ports that are off are unused)"
for m in 0 1 2 3 4; do
  echo "lint: pipe_reg MODE $m"; verilator --lint-only $W -Wno-DECLFILENAME -Wno-UNUSEDPARAM --top-module pipe_reg -GMODE=$m -GN=2 -GTLAST_EN=1 -GTKEEP_EN=1 -GTUSER_W=4 pipe_reg/rtl/*.sv
done
echo "lint: credit_chan"; verilator --lint-only $W -Wno-DECLFILENAME -Wno-UNUSEDPARAM --top-module credit_chan -GCREDITS=5 -GLF=2 -GLB=2 credit_chan/rtl/credit_chan.sv
for t in axil_reg_slice axi4_reg_slice; do
  echo "lint: $t"; verilator --lint-only $W -Wno-DECLFILENAME -Wno-UNUSEDPARAM --top-module "$t" axi_reg_slice/rtl/$t.sv pipe_reg/rtl/*.sv
done
echo "lint: clean"
