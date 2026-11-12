# results/b63d: brief 63D, the tri-mode MAC 0.2 and the network blocks

Every number below is copied from the files in this folder or from the entries' `char/xc7a100tcsg324-1.json`.

## Seeded faults

`faults.json` (48 of 48 caught), run by `python3 flow/net/faults.py`:

| Entry | Fault | Result |
|---|---|---|
| arp_responder | `arp_reply_wrong_opcode` | caught |
| arp_responder | `arp_answers_any_address` | caught |
| arp_responder | `arp_round_robin_stuck` | caught |
| arp_responder | `arp_bad_frames_accepted` | caught |
| arp_responder | `arp_no_holdoff` | caught |
| eth_mac_rgmii | `rx_ddr_nibbles_swapped` | caught |
| eth_mac_rgmii | `rx_nibble_alignment_ignores_sfd` | caught |
| eth_mac_rgmii | `rgmii_rx_crc_skips_first_byte` | caught |
| eth_mac_rgmii | `rgmii_rx_runt_not_flagged` | caught |
| eth_mac_rgmii | `rgmii_tx_short_ifg` | caught |
| eth_mac_rgmii | `tx_no_padding` | caught |
| eth_mac_rgmii | `tx_underrun_not_poisoned` | caught |
| eth_mac_rgmii | `tx_10_100_nibbles_swapped` | caught |
| eth_mac_rgmii | `sf_commits_bad_frames` | caught |
| eth_mac_rgmii | `sf_keeps_fcs` | caught |
| eth_mac_rgmii | `filter_hash_wrong_bits` | caught |
| eth_mac_rgmii | `filter_broadcast_always` | caught |
| eth_mac_rgmii | `vlan_strip_leaves_tci` | caught |
| eth_mac_rgmii | `pause_quanta_half` | caught |
| eth_mac_rgmii | `pause_not_honoured` | caught |
| eth_mac_rgmii | `pause_frame_wrong_opcode` | caught |
| eth_mac_rgmii | `control_frames_forwarded` | caught |
| eth_mac_rgmii | `stats_octets_without_fcs` | caught |
| eth_mac_rgmii | `stats_mcast_counts_broadcast` | caught |
| eth_mac_rgmii | `jumbo_length_11_bits` | caught |
| icmp_echo | `icmp_ttl_kept` | caught |
| icmp_echo | `icmp_checksum_not_updated` | caught |
| icmp_echo | `icmp_answers_fragments` | caught |
| icmp_echo | `icmp_sum_over_padding` | caught |
| icmp_echo | `icmp_addresses_not_swapped` | caught |
| igmp_join | `igmp_no_router_alert` | caught |
| igmp_join | `igmp_no_suppression` | caught |
| igmp_join | `igmp_leave_always` | caught |
| igmp_join | `igmp_timer_never_restarted` | caught |
| igmp_join | `igmp_ttl_two` | caught |
| ipv4_udp_rx | `udp_rx_highest_port_wins` | caught |
| ipv4_udp_rx | `udp_rx_no_pseudo_header_source` | caught |
| ipv4_udp_rx | `udp_rx_padding_passed` | caught |
| ipv4_udp_rx | `udp_rx_fragments_passed` | caught |
| ipv4_udp_rx | `udp_rx_options_not_skipped` | caught |
| ipv4_udp_tx | `udp_tx_zero_checksum_sent` | caught |
| ipv4_udp_tx | `udp_tx_ident_stuck` | caught |
| ipv4_udp_tx | `udp_tx_length_plus_one` | caught |
| ipv4_udp_tx | `udp_tx_long_payload_sent` | caught |
| mdio_master | `mdio_preamble_31_ones` | caught |
| mdio_master | `mdio_turnaround_driven` | caught |
| mdio_master | `mdio_read_lsb_first` | caught |
| mdio_master | `mdio_release_without_hold` | caught |

## Formal (SymbiYosys)

`formal.json`, Yosys 0.70+385 (git sha1 098e46a36, Release, Clang /usr/bin/clang++ 21.1.8), engine smtbmc boolector. Bounded means bounded model checking to the stated depth, not a proof.

| Entry | Job | What | Result |
|---|---|---|---|
| mdio_master | `mdio.sby prove` | frame position, MDC waveform, line releases and setup/hold: k-induction proof | PASS |
| mdio_master | `mdio.sby cover` | a whole read frame completes | PASS |
| arp_responder | `arp.sby bmc` | 42-byte frames, AXI-Stream rules, lookups answered only when asked: bounded, 60 clocks | PASS |
| arp_responder | `arp.sby cover` | a reply and a request leave | PASS |
| icmp_echo | `icmp.sby bmc` | AXI-Stream rules, no reply without a request: bounded, 40 clocks | PASS |
| icmp_echo | `icmp.sby cover` | a whole reply to a minimal echo request | PASS |
| ipv4_udp_rx | `udp_rx.sby bmc` | AXI-Stream rules with tuser, tdest and header fields; input held after a frame: bounded, 30 clocks | PASS |
| ipv4_udp_rx | `udp_rx.sby cover` | a whole datagram parsed and passed on | PASS |
| ipv4_udp_tx | `udp_tx.sby bmc` | frames of 42 bytes plus the payload, AXI-Stream rules, input held while sending: bounded, 60 clocks | PASS |
| ipv4_udp_tx | `udp_tx.sby cover` | a two-byte datagram leaves | PASS |
| igmp_join | `igmp.sby bmc` | 46-byte frames, AXI-Stream rules: bounded, 60 clocks | PASS |
| igmp_join | `igmp.sby cover` | a report and a leave leave | PASS |
| eth_mac_rgmii | `classify.sby bmc` | the address filter's verdict equals the restated rule: bounded, 12 clocks | PASS |
| eth_mac_rgmii | `classify.sby cover` | a multicast address accepted by the table or the hash | PASS |

## Out-of-context cost (Artix-7 xc7a100tcsg324-1, 8 ns target, Vivado 2026.1)

One routed run per point; Fmax = 1000 / (8 - WNS), an estimate. Not run on a board.

| Entry | Variant | Point | LUT | FF | LUT RAM | Block RAM tiles | Fmax estimate (MHz) |
|---|---|---|---|---|---|---|---|
| eth_mac_rgmii | `bram` | SF_DEPTH 4096, MAX_FRAME 1522 | 1013 | 1564 | 28 | 1 | 143.8 |
| eth_mac_rgmii | `bram` | SF_DEPTH 32768, MAX_FRAME 9216 | 1028 | 1597 | 30 | 8 | 137.9 |
| eth_mac_rgmii | `lutram` | SF_DEPTH 4096, MAX_FRAME 1522 | 1990 | 2092 | 796 | 0 | 136.4 |
| eth_mac_rgmii | `lutram` | SF_DEPTH 32768, MAX_FRAME 9216 | 9026 | 5955 | 6174 | 0 | 124.9 |
| mdio_master | `base` | DIV 2 | 101 | 167 | 0 | 0 | 284.7 |
| mdio_master | `base` | DIV 32 | 99 | 162 | 0 | 0 | 306.6 |
| arp_responder | `base` | CACHE_N 4 | 481 | 866 | 0 | 0 | 133.2 |
| arp_responder | `base` | CACHE_N 16 | 1101 | 1840 | 0 | 0 | 120.0 |
| icmp_echo | `bram` | BUF_BYTES 2048 | 377 | 443 | 0 | 0.5 | 114.5 |
| icmp_echo | `bram` | BUF_BYTES 16384 | 379 | 443 | 0 | 4 | 113.4 |
| icmp_echo | `lutram` | BUF_BYTES 2048 | 871 | 455 | 384 | 0 | 109.2 |
| icmp_echo | `lutram` | BUF_BYTES 16384 | 4405 | 517 | 3072 | 0 | 102.8 |
| ipv4_udp_rx | `base` | N_PORTS 4 | 491 | 416 | 0 | 0 | 74.6 |
| ipv4_udp_rx | `base` | N_PORTS 8 | 527 | 418 | 0 | 0 | 81.1 |
| ipv4_udp_tx | `bram` | MAX_PAYLOAD 1472 | 560 | 251 | 0 | 0.5 | 81.5 |
| ipv4_udp_tx | `bram` | MAX_PAYLOAD 8972 | 532 | 269 | 0 | 4 | 77.7 |
| ipv4_udp_tx | `lutram` | MAX_PAYLOAD 1472 | 914 | 260 | 276 | 0 | 80.4 |
| ipv4_udp_tx | `lutram` | MAX_PAYLOAD 8972 | 2713 | 286 | 1692 | 0 | 74.0 |
| igmp_join | `base` | N_GROUPS 4 | 1075 | 430 | 0 | 0 | 79.8 |
| igmp_join | `base` | N_GROUPS 8 | 1628 | 491 | 0 | 0 | 71.3 |

The MAC points have FILTER, VLAN 2, PAUSE and STATS on, CUT_THROUGH 0 and IO_FAMILY 7series. ipv4_udp_rx, ipv4_udp_tx, igmp_join and icmp_echo miss the 125 MHz of the RGMII MAC; they are used at 50 MHz behind the RMII MAC.

## Board design

[designs/b63d_nexys_net](../../designs/b63d_nexys_net/README.md): simulated through the shell; its Vivado 2026.1 build summary is in `nexys_build/` when present. Not run on the board.
