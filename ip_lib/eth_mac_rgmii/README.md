# eth_mac_rgmii 0.2.0

Tri-mode (10/100/1000 Mb/s) Ethernet MAC for a PHY with an RGMII (reduced gigabit media-independent interface) link: cut-through receive (bytes passed on as they arrive) with the FCS (frame check sequence, the CRC at the end of a frame) verdict at the end, optional store-and-forward AXI-Stream receive, AXI-Stream transmit with padding, FCS and inter-frame gap (IFG); the receive clock crossing inside. Optional (off by default): receive address filter (own unicast, broadcast, promiscuous, multicast by exact table and 64-bin hash), VLAN tag report and strip, IEEE 802.3x pause (honoured and sent), statistics counters, jumbo frames up to 9216 bytes.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: Meets 125 MHz out of context with the block RAM buffer (139-141 MHz estimated); the LUT RAM buffer meets it only just in one run at 32768 bytes (WNS 0.04 ns, within run-to-run noise). Simulated (0.1.0 and 0.2.0 features, with an independent adversarial pause bench); formal checks of the frame FSMs (bounded) and the address filter; built alone on an Artix-7 with Vivado 2026.1; 0.1.0 synthesised and routed inside the KR260 trading-path design; not yet run on a board (its filter and statistics blocks are in the Nexys A7 network design behind eth_mac_rmii, built, not yet run).

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `CUT_THROUGH` | 1 | 0, 1 | 1 = cut-through view only; 0 = also the store-and-forward buffer and m_axis |
| `MIN_FRAME` | 64 | 18..2000 | receive: shortest good frame, FCS included |
| `MAX_FRAME` | 1522 | 64..9216 | receive: longest good frame, FCS included; above 2000 (jumbo frames) rx_idx and rx_end_len widen to 14 bits |
| `MIN_DATA` | 60 | 1..1514 | transmit: pad to this many bytes before the FCS |
| `IFG_BYTES` | 12 | 1..255 | transmit: idle byte times after the FCS (the gap is one more when a frame is waiting) |
| `SF_DEPTH` | 4096 | 2048..65536, power of two | store-and-forward buffer in bytes (CUT_THROUGH = 0): at least two frames of MAX_FRAME (32768 for 9216-byte jumbo frames) |
| `FILTER` | 0 | 0, 1 | 1 = receive address filter (eth_rx_classify) |
| `MC_EXACT` | 4 | 0..16 | exact-match multicast table entries (FILTER = 1) |
| `VLAN` | 0 | 0, 1, 2 | 0 = none; 1 = report a tag (rx_end_vlan, rx_end_tci); 2 = also strip it from the store-and-forward output |
| `PAUSE` | 0 | 0, 1 | 1 = IEEE 802.3x pause: received pause frames honoured, pause_req sends one; MAC control frames consumed |
| `STATS` | 0 | 0, 1 | 1 = statistics counters (eth_mac_stats) |
| `STAT_W` | 32 | 16..64 | counter width (STATS = 1) |
| `RX_RAM` | bram | bram, lutram | the store-and-forward buffer: block RAM or LUT RAM (the implementation variants) |
| `IO_FAMILY` | ultrascale | ultrascale, 7series | DDR input and output registers: IDDRE1/ODDRE1 (UltraScale, UltraScale+) or IDDR/ODDR (7-series) |

Constraints: `MIN_FRAME <= MAX_FRAME`; `SF_DEPTH >= 2 * MAX_FRAME or CUT_THROUGH == 1`; `VLAN != 2 or CUT_THROUGH == 0`; `MIN_DATA <= 60 or PAUSE == 0`.

Out-of-space values fail at elaboration with `$error` (tested: `CUT_THROUGH=2`, `MIN_FRAME=17`, `MAX_FRAME=9217`, `CUT_THROUGH=0, SF_DEPTH=3000`, `MIN_DATA=0`, `IFG_BYTES=0`, `FILTER=2`, `MC_EXACT=17`, `VLAN=3`, `VLAN=2, CUT_THROUGH=1`, `PAUSE=2`, `STATS=2`, `STAT_W=15`, `RX_RAM=uram`, `IO_FAMILY=versal`, `CUT_THROUGH=0, MAX_FRAME=9216, SF_DEPTH=16384`).

## Interfaces

- `rgmii`: native; rgmii_rx_clk, rgmii_rxd[3:0], rgmii_rx_ctl, rgmii_txc, rgmii_txd[3:0], rgmii_tx_ctl
- `rx_ct`: native; rx_sof_pulse, rx_valid, rx_sof, rx_data[7:0], rx_idx, rx_end_valid, rx_end_good, rx_end_fcs_err, rx_end_runt, rx_end_giant, rx_end_er, rx_end_len (11 bits; 14 when MAX_FRAME > 2000), rx_da_valid, rx_da_match, rx_end_filtered, rx_end_bcast, rx_end_mcast, rx_end_vlan, rx_end_tci[15:0], rx_end_ctrl, rx_end_pause. cut-through view, always present: every frame byte (FCS included) one clock after mac_rx takes it, before the frame is known good; the verdict follows the last byte. No back-pressure
- `m_axis`: axis (dir master, tdata 8, tready True). store-and-forward, CUT_THROUGH = 0 only; good frames without their FCS; bad and overflowing frames dropped and counted (rx_sf_dropped, rx_sf_overflow); with FILTER = 1 rejected frames and with PAUSE = 1 MAC control frames are dropped too; with VLAN = 2 a tag is removed and its TCI rides beside every byte (m_axis_tci, m_axis_tagged)
- `s_axis`: axis (dir slave, tdata 8, tuser 1). a frame must keep coming once started (an underrun ends it with a bad FCS, tx_underrun); tuser or tx_poison marks the frame bad (inverted FCS)
- `config`: native; mac_addr[47:0], promisc, bcast_en, mcast_all, mc_hash[63:0], mc_we, mc_idx[3:0], mc_addr[47:0], mc_en, pause_req, pause_quanta[15:0], tx_paused, tx_pause_sent, stat_clear, stat_addr[4:0], stat_data[STAT_W-1:0]. static while frames pass (the exact table is written one entry per clock); tie them when the feature is off. The statistics are 21 wrapping counters, listed in rtl/eth_mac_stats.sv, read one clock after stat_addr

Clocks: `clk` (125 MHz at every speed), `clk90` (clk, 90 degrees later (forms TXC)), `rgmii_rx_clk` (the PHY's RX_CLK (125, 25 or 2.5 MHz), on a clock buffer). Reset: `rst`, active high, synchronous.

## Latency and throughput

- rx: cut-through: a byte leaves rx_* one 8 ns clock after it leaves the clock-crossing FIFO. In a looped simulation the transmit MAC's first preamble byte reaches the receive MAC as its SFD (start-of-frame delimiter) 17 clocks (136 ns) later: 8 of them are the preamble and SFD themselves, the rest the RGMII pins and the clock-crossing FIFO, which is a simulation model, so its real latency is unmeasured (results/b58a/pins_sim.json). Store-and-forward: the whole frame, then the first byte on m_axis 4 clocks after rx_end_valid when the buffer was empty (the variants' declared latency; measured in flow/net/tests/mac_rgmii_cocotb.py)
- tx: first preamble byte on the MAC's output 2 clocks after s_axis_tvalid while idle; 2 more to TX_CTL at the pins (a register and the ODDRE1, simulation model; results/b58a/pins_sim.json)
- throughput: line rate at 10, 100 and 1000 Mb/s; frames offered back to back leave IFG_BYTES + 1 idle byte times apart (flow/net/tests/mac_rgmii_cocotb.py)

## Evidence

cocotb against a Python RGMII PHY model written from RGMII v2.0 and IEEE 802.3 (zlib's CRC-32 for the FCS) and a model of the 0.2 features written from IEEE 802.3 and 802.1Q (model.py), Icarus Verilog 12; 0.1.0's tests at 1000, 100 and 10 Mb/s in both directions with every new feature off; the filter under three settings with frame-by-frame flags, the store-and-forward output with tags stripped, every statistics counter and a clear, pause honoured (hold time measured in byte times at 1000 and 100 Mb/s) and sent ahead of waiting data, and 9000-byte MTU jumbo frames; an independent adversarial bench adds a pause received mid-frame and a zero-quanta pause ending a long one, and a pause requested while a pause frame is on the wire. Tests: `flow/net/tests/test_58_mac_rgmii_rtl.py`, `flow/net/tests/test_63d_adversarial_rtl.py`, `flow/net/tests/test_63d_formal.py`.

Try it: `python3 -m pytest flow/net/tests/test_58_mac_rgmii_rtl.py flow/net/tests/test_63d_adversarial_rtl.py flow/net/tests/test_63d_formal.py` (the formal jobs need SymbiYosys on PATH; they are skipped without it).

Parameter points simulated: `CUT_THROUGH=1`; `CUT_THROUGH=0, SF_DEPTH=4096`; `CUT_THROUGH=0, SF_DEPTH=2048, MIN_FRAME=60, MAX_FRAME=1000, MIN_DATA=46, IFG_BYTES=16`; `CUT_THROUGH=0, FILTER=1, VLAN=2, PAUSE=1, STATS=1`; `CUT_THROUGH=0, SF_DEPTH=2048, MAX_FRAME=1000, RX_RAM=lutram, FILTER=1, MC_EXACT=1, VLAN=1, STATS=1, STAT_W=16`; `CUT_THROUGH=1, FILTER=1, MC_EXACT=0, VLAN=1, PAUSE=1, STATS=1`; `CUT_THROUGH=0, MAX_FRAME=9216, SF_DEPTH=32768, VLAN=2, STATS=1`.

Terms (ARP, ICMP, IGMP, MDIO, RMII, RGMII, VLAN, pause, OOC, WNS, Fmax) are defined in [the library's terms](../README.md#terms).

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `rx_ddr_nibbles_swapped` | at 1000 Mb/s the rising-edge nibble is taken as the upper half of the byte | caught |
| `rx_nibble_alignment_ignores_sfd` | at 10/100 Mb/s bytes are aligned on the preamble instead of the SFD | caught |
| `rgmii_rx_crc_skips_first_byte` | the FCS check is computed over one byte too few | caught |
| `rgmii_rx_runt_not_flagged` | frames shorter than MIN_FRAME are not reported as runts | caught |
| `rgmii_tx_short_ifg` | the inter-frame gap is one byte time short | caught |
| `tx_no_padding` | short frames are sent without padding to MIN_DATA | caught |
| `tx_underrun_not_poisoned` | a frame cut short by an AXI-Stream underrun leaves with a good FCS | caught |
| `tx_10_100_nibbles_swapped` | at 10/100 Mb/s the upper nibble is sent first | caught |
| `sf_commits_bad_frames` | the store-and-forward buffer passes frames with a bad FCS | caught |
| `sf_keeps_fcs` | the store-and-forward output includes the FCS bytes | caught |
| `filter_hash_wrong_bits` | the multicast hash takes the wrong six bits of the CRC | caught |
| `filter_broadcast_always` | broadcast frames pass the filter with bcast_en off | caught |
| `vlan_strip_leaves_tci` | stripping removes the TPID but leaves the TCI bytes in the frame | caught |
| `pause_quanta_half` | a pause quantum is taken as 256 bit times instead of 512 | caught |
| `pause_not_honoured` | a received pause does not hold transmit frames back | caught |
| `pause_frame_wrong_opcode` | the pause frame sent carries opcode 0x0002 instead of 0x0001 | caught |
| `control_frames_forwarded` | MAC control frames reach the store-and-forward output instead of being consumed | caught |
| `stats_octets_without_fcs` | the good-octet counter leaves out the FCS | caught |
| `stats_mcast_counts_broadcast` | broadcast frames are also counted as multicast | caught |
| `jumbo_length_11_bits` | with jumbo frames the length counters stay 11 bits wide and saturate at 2047 | caught |
| `pause_zero_quanta_ignored` | a pause of zero quanta does not end a pause in progress (found by the independent review) | caught |
| `pause_quanta_not_latched` | a pause request arriving while a pause frame is sent changes that frame's quanta bytes mid-frame | caught |

## Variants

Selected by `RX_RAM`; every variant has the same ports, the same bit-exact result and the same tests. Latency is clocks from an accepted input to its result; II (initiation interval) is clocks between accepted inputs, 1 meaning a new input every clock.

| Variant | What | Latency | II | Use when |
|---|---|---|---|---|
| `bram` | the store-and-forward buffer in block RAM | `4` | `1` | the default; measured: 1 block RAM tile at SF_DEPTH 4096, 8 at 32768, about 139-141 MHz |
| `lutram` | the store-and-forward buffer in LUT RAM | `4` | `1` | block RAM spoken for and small buffers; measured: 796 LUTs as RAM at 4096 (about 133 MHz), 6174 at 32768, where it meets 125 MHz only just in one run (WNS 0.04 ns) |

Measured at CUT_THROUGH 0, MIN_FRAME 64, MAX_FRAME 1522, MIN_DATA 60, IFG_BYTES 12, SF_DEPTH 4096, FILTER 1, MC_EXACT 4, VLAN 2, PAUSE 1, STATS 1, STAT_W 32, IO_FAMILY 7series: built alone (out of context) on an Artix-7, xc7a100tcsg324-1, for a 8.0 ns clock (125 MHz), Vivado 2026.1 (build 6511674). Not run on a board.

| Variant | DSP | Block RAM tiles | LUT | Fmax estimate (MHz) | II | Latency |
|---|---|---|---|---|---|---|
| `bram` | 0 | 1 | 1015 | 139 | 1 | 4 |
| `lutram` | 0 | 0 | 1989 | 133 | 1 | 4 |

Fmax is estimated from one routed run at the target clock (1000 / (period - WNS)); it is not a closure at that frequency. WNS (worst slack against the clock) below zero means the target was missed.

<details><summary>Every measured point (4 rows; source: <a href="char/xc7a100tcsg324-1.json">char/xc7a100tcsg324-1.json</a>)</summary>

| Variant | CUT_THROUGH | MIN_FRAME | MAX_FRAME | MIN_DATA | IFG_BYTES | SF_DEPTH | FILTER | MC_EXACT | VLAN | PAUSE | STATS | STAT_W | IO_FAMILY | LUT | FF | LUT RAM | Block RAM tiles | DSP | WNS (ns) | Fmax estimate (MHz) | Dynamic power (W) | Latency | II |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `bram` | 0 | 64 | 1522 | 60 | 12 | 4096 | 1 | 4 | 2 | 1 | 1 | 32 | 7series | 1015 | 1580 | 28 | 1 | 0 | 0.802 | 138.9 | 0.021 | 4 | 1 |
| `bram` | 0 | 64 | 9216 | 60 | 12 | 32768 | 1 | 4 | 2 | 1 | 1 | 32 | 7series | 1028 | 1613 | 30 | 8 | 0 | 0.901 | 140.9 | 0.030 | 4 | 1 |
| `lutram` | 0 | 64 | 1522 | 60 | 12 | 4096 | 1 | 4 | 2 | 1 | 1 | 32 | 7series | 1989 | 2108 | 796 | 0 | 0 | 0.473 | 132.9 | 0.029 | 4 | 1 |
| `lutram` | 0 | 64 | 9216 | 60 | 12 | 32768 | 1 | 4 | 2 | 1 | 1 | 32 | 7series | 9027 | 5993 | 6174 | 0 | 0 | 0.040 | 125.6 | 0.092 | 4 | 1 |

Dynamic power is vectorless (default toggle rates, no simulation activity): use it to rank variants, not as a measurement. Regenerate with `python3 -m flow.ipchar eth_mac_rgmii` (Vivado, minutes per point).

</details>

## Boundary and reuse

- Registered outputs: RGMII data and control through ODDRE1/IDDRE1 (behavioural models in simulation); rx_*, m_axis and the MAC's GMII side are registers.
- Clock crossings: one crossing, RX_CLK to clk: an xpm_fifo_async (16 entries, 2 synchroniser stages), the receive reset by xpm_cdc_sync_rst and the speed setting by xpm_cdc_array_single; TXC's waveform moves from clk to clk90 through one register.
- Part, board or pin: IDDRE1/ODDRE1 (IO_FAMILY ultrascale) or IDDR/ODDR (IO_FAMILY 7series) under `ifdef SYNTHESIS`; the input delay (IDELAYE3) is UltraScale only. Pins, IO standards, RGMII delay mode and the RX clock buffer are the board's (the project knowledge base, board/kr260/ethernet).
- Depends on: eth_mac_rmii.
- Limits: formal checks of the frame state machines are bounded (20 and 40 clocks), not proofs, and the address filter is checked by bounded model checking against the rule restated in the harness; full duplex only; no half duplex, no priority flow control (802.1Qbb), no IEEE 1588 timestamps beyond the SOF pulses; VLAN stripping removes one tag only and only from the store-and-forward output; the MDIO master is a separate entry (mdio_master); 10/100 nibble alignment needs the SFD; RGMII input timing is closed only for the PHY's internal RX delay mode (board XDC); not yet run on a board; the multicast hash bin is the 6 least significant bits of the reflected CRC-32 register over the destination (ether_crc_le(6, addr) & 0x3f in Linux), not the bit-reversed index some MACs use, so a driver filling mc_hash must use the same; VLAN = 2 strips only the outer tag of a double-tagged frame (the inner tag stays in the frame; m_axis_tci is the outer TCI); a 64-byte tagged frame leaves the store-and-forward output as 56 bytes, under the 60-byte Ethernet minimum (the consumer pads if it forwards it); with FILTER and PAUSE, consumed pause frames are not counted as filtered.

## Cost table

measured costs are in the Variants section above (the 0.1.0 trading-path build on the KR260 is in results/b58a).

Licence: MIT (this repository).
