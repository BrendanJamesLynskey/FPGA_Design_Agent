# ip_lib: the project's own IP library

Library modules that pass the library's reuse checks: a declared parameter space (`ip.yaml`), elaboration guards,
tests at several points of that space, standard interfaces at the boundary, no hidden clock crossing, nothing tied to a
part or a pin. Each entry holds `rtl/`, `tb/`, `ip.yaml`, a generated `README.md` and a `CHANGELOG.md`. All of it is our
own code under the repository's MIT licence.

## Implementation variants

An entry can hold several implementations of one block (same ports, parameters, model and tests); they differ in
resources, latency, throughput and Fmax. Each is measured built alone (out of context) with Vivado 2026.1 on an
Artix-7 only, and none has run on a board yet.

Try it: `python3 -m flow.ipvariants fir --budget dsp=0` ranks the FIR's variants against a plan that has no DSP slices
left. `python3 -m flow.ipchar <entry>` measures an entry (runs Vivado; minutes per point). The format, the terms and the
read API are in [docs/ip_variants.md](../docs/ip_variants.md).

| Entry | Variants | Tests |
|---|---|---|
| [fir](fir/README.md) | `dsp_bram`, `dist_ram`, `serial`, `lut_mult`: folded DSP MACs with block RAM or LUT RAM, one time-shared DSP MAC, a fully parallel LUT-multiplier form | all four bit-exact against `fir/model.py` at four parameter points, measured latency and II equal the declared ones, a differential test across the variants, an adversarial bench (coefficient beats between samples, reloads with results in flight, resets mid-stream), ten seeded faults |
| [dds_awg](dds_awg/README.md) | `bram`, `lut`: the sine table in block RAM or in LUTs | the existing tests at both variants |
| [adc_histogram](adc_histogram/README.md) | `dist_ram`, `bram`: the bins in LUT RAM, or in two block RAM copies | the existing tests at both variants |
| [eth_mac_rgmii](eth_mac_rgmii/README.md) | `bram`, `lutram` (`RX_RAM`): the store-and-forward buffer | 0.2's filter and statistics tests at both; jumbo at `bram` |
| [icmp_echo](icmp_echo/README.md) | `bram`, `lutram` (`RAM`): the frame buffer | the echo tests at both |
| [ipv4_udp_tx](ipv4_udp_tx/README.md) | `bram`, `lutram` (`RAM`): the payload buffer | the transmit tests at both |

Run: `python3 -m pytest ip_lib/fir/tb/test_fir_rtl.py flow/tests/test_63a_ipvariants.py` (Icarus Verilog 12, cocotb
2.0.1); faults: `python3 hil/ip_faults.py --blocks fir`.

## Networking and packet processing

Byte-wide AXI-Stream blocks, simulated bit-exact against Python golden models with pcap traffic. Status: simulated
against Python models. The packet-processing blocks in this table other than the two MACs have no out-of-context cost
table, xsim cross-check or board run yet; `eth_mac_rgmii` and the protocol blocks in the next table do have
out-of-context costs.

| Entry | What | Tests |
|---|---|---|
| [eth_mac_rmii](eth_mac_rmii/README.md) | 10/100 MAC for an RMII PHY (Nexys A7 LAN8720A): preamble/SFD, FCS generate, check and strip, padding, inter-frame gap | RX and TX bit-exact at 10 and 100 Mb/s, loopback, underrun |
| [eth_mac_rgmii](eth_mac_rgmii/README.md) | tri-mode 10/100/1000 MAC for an RGMII PHY (the KR260's): cut-through or store-and-forward receive, AXI-Stream transmit; optional filter, VLAN, pause, statistics, jumbo frames (see its README) | 0.1.0's points at 3 speeds; 4 more points for the 0.2 features (cocotb) |
| [pkt_parser](pkt_parser/README.md) | streaming parser: Ethernet, 0-2 VLAN tags, IPv4 (checksum, options, fragments), IPv6, UDP/TCP ports; header word beside the stream | header words bit-exact, cross-checked with scapy |
| [match_exact](match_exact/README.md) | exact match: two-way d-left hash in BRAM plus a CAM stash; insert, delete, age | lookups every clock during updates |
| [match_lpm](match_lpm/README.md) | IPv4 longest-prefix match: 8-8-8-8 multibit trie; Python control plane | against brute-force LPM, incremental routes under traffic |
| [match_ternary](match_ternary/README.md) | ternary match (TCAM emulation) in LUT RAM, lowest index wins | overlapping rules, rewrites under traffic |
| [axil_table_ctrl](axil_table_ctrl/README.md) | AXI4-Lite front end for the three tables | through the table tests |
| [pkt_rewrite](pkt_rewrite/README.md) | action apply: drop, MACs, VLAN push/pop/VID, TTL, IPv4 destination with RFC 1624 checksum updates | bit-exact; checksums re-verified by scapy |
| [pkt_queue_sched](pkt_queue_sched/README.md) | packet buffer, per-queue descriptors, tail drop with counters; RR, strict priority, DRR | departure order bit-exact; loss accounting |
| [l2_switch](l2_switch/README.md) | learning, VLAN-aware 4-port switch (flood, filter, ageing) | egress streams bit-exact against a replayed model |

### Protocol blocks: ARP, ICMP, UDP, IGMP, MDIO

ARP maps an IPv4 address to a MAC address; ICMP echo is ping; IGMP tells the network which multicast groups a host
wants; MDIO is the two-wire bus that configures the Ethernet PHY chip. RMII is the 10/100 Mb/s PHY interface on the
Nexys A7, RGMII the gigabit one on the KR260 (more in [Terms](#terms)).

Byte-wide AXI-Stream in and out (Ethernet frames without the FCS, as the MACs give and take them), each against a
Python model written from the RFCs, with scapy as an independent decoder at test time and an independent adversarial
bench. Simulated, checked formally (bounded, except the MDIO frame, which is proved by k-induction at DIV 2), and built
alone out of context on an Artix-7 with Vivado 2026.1. All of them run together behind `eth_mac_rmii` in the Nexys A7
design [designs/b63d_nexys_net](../designs/b63d_nexys_net/README.md), which is built but not yet run on a board.

Timing: at a 125 MHz target, `ipv4_udp_rx`, `ipv4_udp_tx`, `igmp_join` (71-82 MHz estimated) and `icmp_echo`
(89-116 MHz) miss, as does `arp_responder` with 16 entries (116 MHz); the MAC with its LUT RAM buffer at 32768 bytes
meets it only just in one run (WNS 0.04 ns). They close at the Nexys design's 50 MHz; behind the 125 MHz RGMII MAC they need pipelining first.

| Entry | What | Tests |
|---|---|---|
| [mdio_master](mdio_master/README.md) | IEEE 802.3 clause 22 management master (moved here from the 58A design, which keeps its copy) | 3 MDC dividers against a clause 22 PHY model; frame timing proved by k-induction at DIV 2 |
| [arp_responder](arp_responder/README.md) | ARP for one IPv4 address, a small cache (round robin, flush) and a rate-limited requester for next-hop lookups | 3 cache sizes; random requests, replies, probes, malformed and bad frames, lookups, flushes |
| [icmp_echo](icmp_echo/README.md) | answers ping; checksums updated incrementally (RFC 1624); the frame buffer in block RAM or LUT RAM (variants) | 3 points; the model recomputes the checksums from scratch; padding, fragments, options, bad checksums |
| [ipv4_udp_rx](ipv4_udp_rx/README.md) | IPv4 and UDP receive: header checksum, options, fragments refused, UDP checksum with the pseudo-header, port demultiplexing | 3 points; every event counter compared with the model |
| [ipv4_udp_tx](ipv4_udp_tx/README.md) | UDP over IPv4 transmit, store and forward, UDP checksum or none; the buffer in block RAM or LUT RAM (variants) | 3 points up to a 9000-byte MTU; scapy recomputes both checksums |
| [igmp_join](igmp_join/README.md) | IGMPv2 host membership for up to 8 groups (joins, queries, suppression, leaves); IGMPv2 only, no IGMPv3 reports | 3 points; a directed RFC 2236 sequence, every frame compared with the model |

Try it: `python3 -m pytest flow/net/tests/test_63d_*_rtl.py flow/net/tests/test_58_mac_rgmii_rtl.py` (cocotb, Icarus
Verilog 12, scapy); formal: `python3 -m pytest flow/net/tests/test_63d_formal.py` (SymbiYosys); faults:
`python3 flow/net/faults.py`; results: [results/b63d](../results/b63d/README.md).

How the evidence is made:

- **Traffic**: `flow/net/traffic.py` builds seeded frames with scapy (minimum frames, one and two VLAN tags, IPv4 with
  options and fragments, IPv6 with an extension header, UDP, TCP, ICMP, ARP, bad checksums, wrong versions, IHL < 5,
  truncated frames) and can write them as pcap.
- **Golden models**: `flow/net/model.py`, plain Python written from the standards, not from the RTL.
- **Benches**: file-driven, the repository's harness method (`flow/ipgen/harness.py` gap schedules and file format): Python
  writes stimulus and a seeded valid/ready schedule, the bench writes what the design produced, Python compares.
- **Faults**: each entry's `faults.yaml` lists seeded bugs; `python3 flow/net/faults.py` runs the tests against each
  ([results/b40/faults.json](../results/b40/faults.json)).
- **Rates and latency**: `python3 -m flow.net.measure` ([results/b40/measure.json](../results/b40/measure.json)).

Run: `pip install scapy==2.8.0 pytest pyyaml`, Icarus Verilog 12, then `python3 -m pytest flow/net/tests`.

**scapy's licence.** scapy is GPL-2.0-only. It is used here as a test-time tool only: the tests import it to build
and dissect frames; it is not imported by, copied into or shipped with any RTL, generated design or library entry, and
the repository does not redistribute it (CI installs it from PyPI). The library and its tests stay MIT. (Decided
2026-11-11.)

## Instruments for hardware-in-the-loop

Small blocks that sit in the unit under test (behind the test shell) or in another device, and are read from the host.
Simulated against Python models with seeded faults; measured on the Nexys A7-100T inside
[designs/b30_hil_audio](../designs/b30_hil_audio) ([results/b30](../results/b30/README.md)).

| Entry | What | Tests |
|---|---|---|
| [freq_duty_counter](freq_duty_counter/README.md) | edges and high clocks of an asynchronous input over a fixed gate | against generated square waves; 1000.0 Hz read on the board |
| [frame_crc](frame_crc/README.md) | CRC-32, pixel count and sum of every frame, compared with the model's CRC | bit-exact against `zlib.crc32`; the model's CRC read back on the board, a seeded pixel fault counted |
| [dds_awg](dds_awg/README.md) | DDS stimulus: sine, triangle, saw, square, amplitude shift | bit-exact against the model; 1 kHz sine measured at the audio jack |
| [logic_analyser](logic_analyser/README.md) | register-mapped capture with level or edge trigger and pre-trigger, read over the shell | known counter; 256 tone samples matched to the DDS model on the board |
| [adc_histogram](adc_histogram/README.md) | code-density histogram for converter DNL and INL | against the model; not yet on a board |

Run: `python -m pytest hil/tests/test_30_ip_rtl.py` (Icarus Verilog 12, cocotb 2.0.1); faults: `python hil/ip_faults.py`;
READMEs: `python flow/net/ipdoc.py`.

## Terms

- **AXI-Stream:** a valid/ready byte stream; a beat moves when both are high, `tlast` marks a frame's last byte, `tuser` on it marks a bad frame.
- **ARP** (Address Resolution Protocol, RFC 826): finds the MAC address that owns an IPv4 address.
- **ICMP echo** (RFC 792): ping; a request and the reply that echoes its data.
- **IGMP** (RFC 2236 for version 2): tells routers which multicast groups a host has joined.
- **MDIO / MDC** (IEEE 802.3 clause 22): the management bus that reads and writes an Ethernet PHY's registers.
- **RMII / RGMII:** the 10/100 Mb/s (2 bits at 50 MHz) and 10/100/1000 Mb/s (4 bits on both edges at 125 MHz) interfaces between a MAC and a PHY.
- **VLAN tag** (IEEE 802.1Q): 4 bytes after the source address carrying a virtual-LAN number (the TCI).
- **Pause** (IEEE 802.3x): a MAC control frame asking the other end to stop sending for a number of 512-bit-time quanta.
- **Multicast hash:** a 64-bit table indexed by 6 bits of the destination address's CRC; a set bit accepts every address that falls in that bin.
- **OOC (out of context):** a block synthesised, placed and routed on its own, without pins or the rest of a design.
- **WNS (worst negative slack):** the timing margin at the target clock; below zero the target is missed.
- **WHS (worst hold slack):** the same for hold: how long data stays steady after the capturing edge; below zero it changes too soon.
- **Setup multicycle:** a constraint telling the timing tool that data are captured a stated number of clock edges after launch, not on the very next edge.
- **IO-CLOCK, IO-VALUE, IO-FWD-SOURCE:** the flow's I/O-timing gate checks (`flow/io_check.py`): a pin delay referenced to a clock other than the interface's, a delay that differs from the data sheet, and a forwarded clock defined from the wrong pin.
- **Fmax estimate:** 1000 / (period - WNS) from one routed run at the target clock; an estimate, not a closure.
