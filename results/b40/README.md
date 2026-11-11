# Brief 40 results: networking and packet processing, simulation phase (2026-11-11)

Every number here is in `measure.json` (made by `python3 -m flow.net.measure`) or `faults.json` (made by
`python3 flow/net/faults.py`). Simulator: Icarus Verilog 12. Clocks are counted in simulation; packets per second
are those counts converted at a stated clock, not a measured Fmax (the OOC synthesis runs are still to do).

## Line rate and latency

Theory: a minimum Ethernet frame takes 84 byte times on the wire (64 + 8 preamble/SFD + 12 gap): 148,809 frames/s at
100 Mb/s, 1,488,095 at 1 Gb/s. A byte-wide block needs 125 MHz for 1 Gb/s.

| Block | Measured | Meaning |
|---|---|---|
| RMII MAC receive | 200 of 200 back-to-back minimum frames out, 336 clocks a frame at 50 MHz | 148,810 frames/s = the 100 Mb/s theory |
| Parser | 60 clocks per 60-byte frame; data latency 1 clock; header word 38 clocks after the first byte (IPv4/UDP minimum frame) | 1 byte a clock, no per-packet gap; cut-through |
| Rewrite | 60 clocks per 60-byte frame; latency 3 clocks | cut-through (two-byte checksum window) |
| Queues and scheduler | 62 clocks per 60-byte frame out; first byte out 63 clocks after the first byte in | store-and-forward: latency = length + 3; 2 clocks a packet overhead |
| L2 switch core | 72 clocks per minimum frame under backlog | 4.67 ports of 100 Mb/s at minimum frames at 50 MHz; 9.33 at 100 MHz |

At full load (four ports offering a byte every clock) the switch took 113 of 240 frames
and counted 127 ingress drops: every frame accounted for.

## Tables

| Table | Lookups | Lookup latency | Update cost at the core |
|---|---|---|---|
| Exact (KEY_W 48, IDX_W 10 (2 x 1024 buckets), STASH 4) | 1 a clock | 3 clocks | insert 5, delete 5, age sweep 2050 clocks; 600 of 600 random keys inserted |
| LPM (strides 8-8-8-8, L1/L2/L3 = 16/32/64 nodes) | 1 a clock | 10 clocks | 1 clock a word; 250 routes compile to 5513 words |
| Ternary (KEY_W 40, CHUNK_W 5, 32 entries) | 1 a clock | 4 clocks | write 34, delete 1 clocks |

Through AXI4-Lite (staging writes, CMD, STATUS poll) an exact-table command took a median of
37 clocks.

## Seeded faults

28 of 28 caught. Per fault:

| Block | Fault | Result |
|---|---|---|
| eth_mac_rmii | `rx_crc_skips_first_byte` | caught |
| eth_mac_rmii | `rx_ends_on_first_low_crs_dv` | caught |
| eth_mac_rmii | `rx_runt_not_flagged` | caught |
| eth_mac_rmii | `tx_pad_fcs_not_inverted` | caught |
| eth_mac_rmii | `tx_short_ifg` | caught |
| l2_switch | `no_learning` | caught |
| l2_switch | `flood_back_to_ingress` | caught |
| l2_switch | `no_ingress_vlan_filter` | caught |
| match_exact | `stash_never_searched` | caught |
| match_exact | `bank1_never_used` | caught |
| match_exact | `age_removes_used` | caught |
| match_lpm | `best_match_not_kept` | caught |
| match_lpm | `wrong_key_byte_level2` | caught |
| match_ternary | `highest_index_wins` | caught |
| match_ternary | `care_mask_ignored` | caught |
| match_ternary | `action_written_early` | caught |
| pkt_parser | `ipv4_options_ignored` | caught |
| pkt_parser | `csum_carry_dropped` | caught |
| pkt_parser | `one_vlan_tag_only` | caught |
| pkt_parser | `fragment_offset_ignored` | caught |
| pkt_parser | `truncation_not_flagged` | caught |
| pkt_queue_sched | `overflow_not_counted` | caught |
| pkt_queue_sched | `drr_no_subtract` | caught |
| pkt_queue_sched | `strict_priority_inverted` | caught |
| pkt_queue_sched | `space_freed_early` | caught |
| pkt_rewrite | `rfc1624_without_complement` | caught |
| pkt_rewrite | `udp_zero_checksum_rewritten` | caught |
| pkt_rewrite | `pop_loses_tlast` | caught |

## Found while building

- LPM control plane: recompiling the trie after adding one route renumbered nodes and so rewrote hundreds of live words, which
  broke lookups in flight; node indices now stay stable across incremental compiles (`model.lpm_compile(alloc=)`).
- Ternary table: the action RAM was written when a rewrite started while a lookup that matched the old rule could
  still read it a clock later; the action is now written when the rule becomes valid again (fault
  `action_written_early` keeps the test honest).
- Rewrite: a frame ending inside a popped VLAN tag lost its TLAST (fault `pop_loses_tlast`).
- L2 switch: ingress drops on several ports in the same clock were counted once (an OR of pulses); now per port.
- Icarus 12: an `always_comb` that calls a function on an X input looped forever at time 0 in `match_exact`; the
  hash is now a continuous assignment.

## Files

- `measure.json`, `faults.json`: the numbers above.
- `pcap/`: the sample traffic and the expected rewrite output (`flow/net/make_pcaps.py`); tests check the RTL against
  both.
