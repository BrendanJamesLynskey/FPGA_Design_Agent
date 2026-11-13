# Results for the Ethernet MAC 0.2 and the network blocks

Brief 63D's records for the Ethernet MAC 0.2 and the network blocks (MDIO, ARP, ICMP echo, IPv4/UDP receive and transmit, IGMPv2): out-of-context timing and cost, seeded faults, formal jobs and the Nexys A7 network design build. Every number below is copied from the files in this folder or from the entries' `char/xc7a100tcsg324-1.json`.

## Timing at a glance

Out of context on an Artix-7 (xc7a100tcsg324-1), Vivado 2026.1, one routed run per point. Fmax estimate = 1000 / (period - WNS). The 125 MHz column asks whether the block could sit behind the RGMII MAC's 125 MHz clock.

| Entry | Target clock | Fmax estimate (MHz), lowest to highest point | Meets 125 MHz? |
|---|---|---|---|
| eth_mac_rgmii | 8 ns (125 MHz) | 125.6 - 140.9 | yes |
| mdio_master | 4 ns (250 MHz) | 284.7 - 306.6 | yes |
| arp_responder | 8 ns (125 MHz) | 115.6 - 128.4 | at some points (see below) |
| icmp_echo | 8 ns (125 MHz) | 88.6 - 116.4 | no |
| ipv4_udp_rx | 8 ns (125 MHz) | 74.6 - 81.1 | no |
| ipv4_udp_tx | 8 ns (125 MHz) | 74 - 81.5 | no |
| igmp_join | 8 ns (125 MHz) | 71.3 - 79.8 | no |

## Seeded faults

`faults.json`: 56 of 56 caught, run by `python3 flow/net/faults.py`.

| Entry | Fault | Result |
|---|---|---|
| arp_responder | `arp_reply_wrong_opcode` | caught |
| arp_responder | `arp_answers_any_address` | caught |
| arp_responder | `arp_round_robin_stuck` | caught |
| arp_responder | `arp_bad_frames_accepted` | caught |
| arp_responder | `arp_no_holdoff` | caught |
| arp_responder | `arp_learns_gratuitous_unknown` | caught |
| arp_responder | `arp_learns_own_ip_claim` | caught |
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
| eth_mac_rgmii | `pause_zero_quanta_ignored` | caught |
| eth_mac_rgmii | `pause_quanta_not_latched` | caught |
| icmp_echo | `icmp_ttl_kept` | caught |
| icmp_echo | `icmp_checksum_not_updated` | caught |
| icmp_echo | `icmp_answers_fragments` | caught |
| icmp_echo | `icmp_sum_over_padding` | caught |
| icmp_echo | `icmp_addresses_not_swapped` | caught |
| icmp_echo | `icmp_back_to_back_overwrite` | caught |
| igmp_join | `igmp_no_router_alert` | caught |
| igmp_join | `igmp_no_suppression` | caught |
| igmp_join | `igmp_leave_always` | caught |
| igmp_join | `igmp_timer_never_restarted` | caught |
| igmp_join | `igmp_ttl_two` | caught |
| igmp_join | `igmp_timer_always_restarted` | caught |
| ipv4_udp_rx | `udp_rx_highest_port_wins` | caught |
| ipv4_udp_rx | `udp_rx_no_pseudo_header_source` | caught |
| ipv4_udp_rx | `udp_rx_padding_passed` | caught |
| ipv4_udp_rx | `udp_rx_fragments_passed` | caught |
| ipv4_udp_rx | `udp_rx_options_not_skipped` | caught |
| ipv4_udp_rx | `udp_rx_last_fragment_passed` | caught |
| ipv4_udp_tx | `udp_tx_zero_checksum_sent` | caught |
| ipv4_udp_tx | `udp_tx_ident_stuck` | caught |
| ipv4_udp_tx | `udp_tx_length_plus_one` | caught |
| ipv4_udp_tx | `udp_tx_long_payload_sent` | caught |
| mdio_master | `mdio_preamble_31_ones` | caught |
| mdio_master | `mdio_turnaround_driven` | caught |
| mdio_master | `mdio_read_lsb_first` | caught |
| mdio_master | `mdio_release_without_hold` | caught |
| icmp_echo | `icmp_tail_bytes_overwritten` | caught |

## Formal (SymbiYosys)

`formal.json`, Yosys 0.70+385 (git sha1 098e46a36, Release, Clang /usr/bin/clang++ 21.1.8), engine smtbmc boolector. Bounded means bounded model checking to the stated depth, not a proof.

| Entry | Job | What | Result |
|---|---|---|---|
| mdio_master | `mdio.sby prove` | frame position, MDC waveform, line releases and setup/hold: k-induction proof | PASS |
| mdio_master | `mdio.sby cover` | a whole read frame completes | PASS |
| arp_responder | `arp.sby bmc` | 42-byte frames, AXI-Stream rules, lookups answered only when asked: bounded, 60 clocks | PASS |
| arp_responder | `arp.sby cover` | a reply and a request leave | PASS |
| icmp_echo | `icmp.sby bmc` | AXI-Stream rules, no reply without a request, and the reply carries the request it answers (byte 13 equal) whatever frame follows it: bounded, 64 clocks; fails at step 60 with the round-1 back-to-back bug restored | PASS |
| icmp_echo | `icmp.sby cover` | a whole reply to a minimal echo request | PASS |
| ipv4_udp_rx | `udp_rx.sby bmc` | AXI-Stream rules with tuser, tdest and header fields; input held after a frame: bounded, 30 clocks | PASS |
| ipv4_udp_rx | `udp_rx.sby cover` | a whole datagram parsed and passed on | PASS |
| ipv4_udp_tx | `udp_tx.sby bmc` | frames of 42 bytes plus the payload, AXI-Stream rules, input held while sending: bounded, 60 clocks | PASS |
| ipv4_udp_tx | `udp_tx.sby cover` | a two-byte datagram leaves | PASS |
| igmp_join | `igmp.sby bmc` | 46-byte frames, AXI-Stream rules: bounded, 60 clocks | PASS |
| igmp_join | `igmp.sby cover` | a report and a leave leave | PASS |
| eth_mac_rgmii | `classify.sby bmc` | the address filter's verdict equals the restated rule: bounded, 12 clocks | PASS |
| eth_mac_rgmii | `classify.sby cover` | a multicast address accepted by the table or the hash | PASS |

## Out-of-context cost, every point

Not run on a board. The MAC points have FILTER, VLAN 2, PAUSE and STATS on, CUT_THROUGH 0 and IO_FAMILY 7series.

| Entry | Variant | Point | Target (ns) | LUT | FF | LUT RAM | Block RAM tiles | WNS (ns) | Fmax estimate (MHz) |
|---|---|---|---|---|---|---|---|---|---|
| eth_mac_rgmii | `bram` | SF_DEPTH 4096, MAX_FRAME 1522 | 8 | 1015 | 1580 | 28 | 1 | 0.802 | 138.9 |
| eth_mac_rgmii | `bram` | SF_DEPTH 32768, MAX_FRAME 9216 | 8 | 1028 | 1613 | 30 | 8 | 0.901 | 140.9 |
| eth_mac_rgmii | `lutram` | SF_DEPTH 4096, MAX_FRAME 1522 | 8 | 1989 | 2108 | 796 | 0 | 0.473 | 132.9 |
| eth_mac_rgmii | `lutram` | SF_DEPTH 32768, MAX_FRAME 9216 | 8 | 9027 | 5993 | 6174 | 0 | 0.04 | 125.6 |
| mdio_master | `base` | DIV 2 | 4 | 101 | 167 | 0 | 0 | 0.487 | 284.7 |
| mdio_master | `base` | DIV 32 | 4 | 99 | 162 | 0 | 0 | 0.738 | 306.6 |
| arp_responder | `base` | CACHE_N 4 | 8 | 497 | 867 | 0 | 0 | 0.214 | 128.4 |
| arp_responder | `base` | CACHE_N 16 | 8 | 1148 | 1841 | 0 | 0 | -0.648 | 115.6 |
| icmp_echo | `bram` | BUF_BYTES 2048 | 8 | 391 | 443 | 0 | 0.5 | -0.59 | 116.4 |
| icmp_echo | `bram` | BUF_BYTES 16384 | 8 | 398 | 443 | 0 | 4 | -0.742 | 114.4 |
| icmp_echo | `lutram` | BUF_BYTES 2048 | 8 | 897 | 455 | 384 | 0 | -1.437 | 106.0 |
| icmp_echo | `lutram` | BUF_BYTES 16384 | 8 | 4557 | 513 | 3072 | 0 | -3.285 | 88.6 |
| ipv4_udp_rx | `base` | N_PORTS 4 | 8 | 491 | 416 | 0 | 0 | -5.412 | 74.6 |
| ipv4_udp_rx | `base` | N_PORTS 8 | 8 | 527 | 418 | 0 | 0 | -4.336 | 81.1 |
| ipv4_udp_tx | `bram` | MAX_PAYLOAD 1472 | 8 | 560 | 251 | 0 | 0.5 | -4.265 | 81.5 |
| ipv4_udp_tx | `bram` | MAX_PAYLOAD 8972 | 8 | 532 | 269 | 0 | 4 | -4.862 | 77.7 |
| ipv4_udp_tx | `lutram` | MAX_PAYLOAD 1472 | 8 | 914 | 260 | 276 | 0 | -4.434 | 80.4 |
| ipv4_udp_tx | `lutram` | MAX_PAYLOAD 8972 | 8 | 2713 | 286 | 1692 | 0 | -5.507 | 74.0 |
| igmp_join | `base` | N_GROUPS 4 | 8 | 1075 | 430 | 0 | 0 | -4.529 | 79.8 |
| igmp_join | `base` | N_GROUPS 8 | 8 | 1628 | 491 | 0 | 0 | -6.033 | 71.3 |

## The Nexys A7 network design

[designs/b63d_nexys_net](../../designs/b63d_nexys_net/README.md): simulated through the shell and built with Vivado 2026.1 with the test shell's protocol 1.1 ([nexys_build/b63d_nexys_net.md](nexys_build/b63d_nexys_net.md)). Every flow gate passes at 50 MHz: WNS 1.569 ns, WHS 0.035 ns (an internal path, `u_arp/ho_ip_reg[15]` to `u_arp/cur_tpa_reg[15]`), 4188 LUTs, 4344 FFs, 2 block RAM tiles, 0.251 W on chip (vectorless), Tj 44.6 C predicted. Not run on a board.

### RMII pin timing

On RMII the PHY sends and samples data on the 50 MHz clock the FPGA gives it, so the pin timing has to be measured from that forwarded clock as it arrives at the PHY, not from the FPGA's own internal clock. The forwarded clock reaches the PHY several nanoseconds late (it passes through the clock manager, a global buffer, an output register and an output buffer), and that delay decides whether receive works. Slack at the pins, from `io_paths_route.txt` (the RMII rev 1.2 figures are used as the bound; the PHY's own data sheet values are to be checked before the board run):

| Path | Setup slack (ns) | Hold slack (ns) |
|---|---|---|
| receive (CRS_DV, RXD, RX_ER) | 1.569 | 1.603 |
| transmit (TX_EN, TXD) | 3.702 | 8.733 |

What makes it work:

- the pin delays are referenced to `eth_refclk`, the clock the FPGA forwards, so the analysis includes its delay (referenced to the internal clock instead, an earlier build reported receive as met when it was not: at the board manual's 45-degree phase receive misses setup by 2.306 ns);
- the forwarded clock leaves at 335.25 degrees, 1.375 ns before the internal clock, which centres the receive window;
- receive data are captured one internal-clock edge later than the tool's default pairing (a setup multicycle of 2; hold stays checked on the edge that really must see the previous data), and transmit data leave from falling-edge registers.

The build declares both RMII interfaces against `eth_refclk` (`build.yaml` io_interfaces), so the I/O gate fails a delay referenced to another clock (IO-CLOCK), a delay that differs from the data sheet (IO-VALUE) and a forwarded clock defined from the wrong pin or not at all (IO-FWD-SOURCE); `designs/b63d_nexys_net/tests/test_b63d_io_constraints.py` checks all three. Terms: [ip_lib/README.md#terms](../../ip_lib/README.md#terms).

## Records

| Path | What |
|---|---|
| `faults.json` | The seeded faults of the network blocks (including the MAC and the later cases) and whether each was caught |
| `formal.json` | The SymbiYosys jobs (bounded checks, one proof and covers) with status, depth and the tool version |
| `nexys_build/` | The Vivado 2026.1 build record and summary of `designs/b63d_nexys_net` |
| the out-of-context cost tables | Read from each entry's `char/xc7a100tcsg324-1.json` under `ip_lib/<entry>/` (not in this folder) |

## Reproduce

- Faults (simulation only): `python3 flow/net/faults.py --json results/b63d/faults.json`.
- Formal: the jobs listed in the Formal table, one `.sby` file per entry under `ip_lib/<entry>/formal/`, run with SymbiYosys.
- Out-of-context points: `python3 -m flow.ipchar <entry>` (Vivado 2026.1, heavy slot); the build of the design: `flow/run_vivado.sh designs/b63d_nexys_net`.
- No board run is involved or possible from these records.

## Known gaps and limits

- Not run on a board: the Nexys A7 design was simulated and built only, and the RMII bounds use the RMII rev 1.2 figures; the PHY's own data sheet values were still to be checked before a board run.
- One routed run per point; most of the application blocks (`icmp_echo`, `ipv4_udp_rx`, `ipv4_udp_tx`, `igmp_join`) do not reach 125 MHz out of context, and `arp_responder` only at some points.
- The formal checks are bounded to the stated depths, apart from the MDIO proof; they are not proofs of the whole behaviour.
- A fault counts as caught when the entry's tests fail on it; the list is what was seeded.
