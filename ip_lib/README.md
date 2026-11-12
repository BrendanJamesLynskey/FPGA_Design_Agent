# ip_lib: the project's own IP library

Library modules that pass the reuse checks of brief 28: a declared parameter space (`ip.yaml`), elaboration guards,
tests at several points of that space, standard interfaces at the boundary, no hidden clock crossing, nothing tied to a
part or a pin. Each entry holds `rtl/`, `tb/`, `ip.yaml`, a generated `README.md` and a `CHANGELOG.md`. All of it is our
own code under the repository's MIT licence.

## Implementation variants (brief 63A)

An entry can hold several implementation variants behind one contract (same ports, parameters, model and tests); they
differ in resources, latency, throughput and Fmax, and each is characterised out of context on Vivado 2026.1. The
schema, the measured data format and the read API for the architecture stage are in
[docs/ip_variants.md](../docs/ip_variants.md); `python3 -m flow.ipvariants fir --budget dsp=0` ranks one entry's
variants against a plan's budget, and `python3 -m flow.ipchar <entry>` measures them (a heavy job).

| Entry | Variants | Tests |
|---|---|---|
| [fir](fir/README.md) | `dsp_bram`, `dist_ram`, `serial`, `lut_mult`: folded DSP MACs with block RAM or LUT RAM, one time-shared DSP MAC, a fully parallel LUT-multiplier form | all four bit-exact against `fir/model.py` at four parameter points, measured latency and II equal the declared ones, a differential test across the variants, nine seeded faults |
| [dds_awg](dds_awg/README.md) | `bram`, `lut`: the sine table in block RAM or in LUTs | the brief-30 tests at both variants |
| [adc_histogram](adc_histogram/README.md) | `dist_ram`, `bram`: the bins in LUT RAM, or in two block RAM copies | the brief-30 tests at both variants |

Run: `python -m pytest ip_lib/fir/tb/test_fir_rtl.py flow/tests/test_63a_ipvariants.py` (Icarus Verilog 12, cocotb
2.0.1); faults: `python hil/ip_faults.py --blocks fir`.

## Networking and packet processing (brief 40)

Byte-wide AXI-Stream blocks, simulated bit-exact against Python golden models with pcap traffic. Status: simulated;
the OOC synthesis cost tables, the xsim cross-check and the hardware-in-the-loop runs are still to do.

| Entry | What | Tests |
|---|---|---|
| [eth_mac_rmii](eth_mac_rmii/README.md) | 10/100 MAC for an RMII PHY (Nexys A7 LAN8720A): preamble/SFD, FCS generate, check and strip, padding, inter-frame gap | RX and TX bit-exact at 10 and 100 Mb/s, loopback, underrun |
| [pkt_parser](pkt_parser/README.md) | streaming parser: Ethernet, 0-2 VLAN tags, IPv4 (checksum, options, fragments), IPv6, UDP/TCP ports; header word beside the stream | header words bit-exact, cross-checked with scapy |
| [match_exact](match_exact/README.md) | exact match: two-way d-left hash in BRAM plus a CAM stash; insert, delete, age | lookups every clock during updates |
| [match_lpm](match_lpm/README.md) | IPv4 longest-prefix match: 8-8-8-8 multibit trie; Python control plane | against brute-force LPM, incremental routes under traffic |
| [match_ternary](match_ternary/README.md) | ternary match (TCAM emulation) in LUT RAM, lowest index wins | overlapping rules, rewrites under traffic |
| [axil_table_ctrl](axil_table_ctrl/README.md) | AXI4-Lite front end for the three tables | through the table tests |
| [pkt_rewrite](pkt_rewrite/README.md) | action apply: drop, MACs, VLAN push/pop/VID, TTL, IPv4 destination with RFC 1624 checksum updates | bit-exact; checksums re-verified by scapy |
| [pkt_queue_sched](pkt_queue_sched/README.md) | packet buffer, per-queue descriptors, tail drop with counters; RR, strict priority, DRR | departure order bit-exact; loss accounting |
| [l2_switch](l2_switch/README.md) | learning, VLAN-aware 4-port switch (flood, filter, ageing) | egress streams bit-exact against a replayed model |

How the evidence is made:

- **Traffic**: `flow/net/traffic.py` builds seeded frames with scapy (minimum frames, one and two VLAN tags, IPv4 with
  options and fragments, IPv6 with an extension header, UDP, TCP, ICMP, ARP, bad checksums, wrong versions, IHL < 5,
  truncated frames) and can write them as pcap.
- **Golden models**: `flow/net/model.py`, plain Python written from the standards, not from the RTL.
- **Benches**: file-driven, the brief-19 harness method (`flow/ipgen/harness.py` gap schedules and file format): Python
  writes stimulus and a seeded valid/ready schedule, the bench writes what the design produced, Python compares.
- **Faults**: each entry's `faults.yaml` lists seeded bugs; `python3 flow/net/faults.py` runs the tests against each
  ([results/b40/faults.json](../results/b40/faults.json)).
- **Rates and latency**: `python3 -m flow.net.measure` ([results/b40/measure.json](../results/b40/measure.json)).

Run: `pip install scapy==2.8.0 pytest pyyaml`, Icarus Verilog 12, then `python3 -m pytest flow/net/tests`.

**scapy's licence.** scapy is GPL-2.0-only. It is used here as a test-time tool only: the tests import it to build
and dissect frames; it is not imported by, copied into or shipped with any RTL, generated design or library entry, and
the repository does not redistribute it (CI installs it from PyPI). The library and its tests stay MIT. (Decision
recorded in brief 40, 2026-11-11.)

## Instruments for hardware-in-the-loop (brief 30)

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
