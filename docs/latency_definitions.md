# Our latencies in industry terms: STAC-T0 and wire-to-wire (brief 109)

Status 2026-11-20. Paper only: no Vivado, no simulation, no board was used. Every number of ours is quoted from a recorded file (named at its use) or
derived from recorded numbers by arithmetic shown here; every industry statement carries a source in the table at the end, with the date it was read.
Anything not read in a primary source is marked **UNCONFIRMED**. This note exists so that nobody compares our 161 ns with the published 13.9 ns
without stating what each one measures.

## The short answer

- Our "tick-to-trade 161 ns" (build `lat_all3`, brief 97C) is **L - E - fibre**: the time from the first bit of a frame arriving at the transceiver pins to the first bit of
  the order leaving them, **plus the optical module's own delay** (unknown, not subtracted), in 6.2058 ns clocks, from stamps inside the FPGA. In STAC-T0's words it is a **FIFO**
  (first in, first out) latency, not an actionable latency.
- The STAC-T0 headline, **13.9 ns**, is the **actionable** latency: from the last bit of the index (the data the decision needs) to the first bit of the order, timestamped
  on the wire by the test harness, minimum over a run, for an Alveo UL3524 card running Exegy's IP.
- The like-for-like figure for our design is derived (not measured) at **about 108 ns for `lat_all3`** (160.5 ns minus 52.8 ns of frame time before the price is complete);
  about 80 % of it is the transceiver, optics and fibre, which our measurement cannot separate. The gap to 13.9 ns is therefore mostly **the transceiver path and its buffers**,
  not the decision logic; the logic net of the frame time is about 19 ns by the same accounting, itself more than 13.9 ns.
- Our counter resolves 6.2 ns and is inside the FPGA; STAC-T0's harness timestamps on the wire. We cannot resolve a 13.9 ns result, and do not claim to.

## 1. Our definitions (from the repo, main at ddc62aa5)

Source: `designs/b96_kr260_10g/docs/design.md` sections 5, 6 and 11; `designs/b96_kr260_10g/docs/register_map.md` (Timestamps, TXV10 to TXV24);
reports 96E, 96F, 96F1, 97, 97C in `_handoff/fpga_agent/reports/`.

**Stamps.** One free-running 32-bit counter in the transmit user clock (TXUSRCLK2, 161.1328125 MHz, 6.2058 ns). A *TX start* is stamped when the preamble word is in the MAC's
output register. An *RX start* is stamped by the receive MAC's start strobe (the clock at which the first word of the frame, the destination address, is in its output register;
the preamble word is not forwarded). Both are inside the FPGA fabric, after the PCS on receive and before it on transmit.

| Quantity | Definition (design.md section 6) | Inside it | Outside it |
|---|---|---|---|
| **E** (echo) | TX start of a probe frame to RX start of the same frame | MAC to PCS to GT transmit (buffers, serialiser), the SFP+ module (both ways), fibre (0.17 m, 0.83 ns), GT receive (CDR, buffers, deserialiser), PCS, MAC to the stamp. The elastic buffer if the build has one (`RATE_MATCH = 1`). | Nothing on the link |
| **L** (loop) | TX start of a feed frame to RX start of the resulting order frame, in the same loopback | E once for the feed, D, and E once for the order | |
| **D** | RX start of the feed to TX start of the order (`TXV24`; also derived as **L - 2E**, not L - E, because the loop crosses the link twice) | Receive MAC output to the decision, the receive-to-transmit crossing, the order builder to the MAC's preamble register | GT, PCS and optics in both directions |
| **Tick-to-trade (board)** | **L - E - fibre** (`results/b97c/README.md`: "(L-E)x6.206 - 0.83 ns"; `docs/latency_reduction.md`: "wire-to-wire on the board is L - E - fibre") | = E + D - fibre: one trip through the whole transmit, link and receive path, plus D | The optics' own delay is **not** subtracted (unknown: design.md section 6) |
| **Tick-to-trade (simulation)** | Clocks from the GT word holding the **price** to the GT word holding the order's **start block** (`core_sim*.json`, `latency_stages.yaml` "tick_to_trade") | Receive PCS, MAC, decision, crossing, transmit MAC and PCS. GT stand-in with zero latency. | The GT, optics, fibre; and the frame time before the price word |

**Why L - E is the wire-to-wire figure at the pins, and what it contains.** Write E = a_tx + O + a_rx, where a_tx is the transmit stamp to the pin (MAC, PCS, GT transmit), O is
everything between the two transceivers (module, fibre, and the module-side and fibre-side analogue parts), and a_rx is the pin to the receive stamp (GT receive, PCS, MAC). The path that matters
in trading is a_rx + D + a_tx (frame in at the pins, order out at the pins). So E + D = (a_rx + D + a_tx) + O, and **L - E = pin-to-pin + O**. Subtracting the fibre leaves the module's delay inside the figure.
This holds if the transmit and receive stamps sit at the same internal points for every frame (they do, by construction) and to the clock-level resolution below. It is an identity of our own stamps, not a
port measurement: no instrument looked at the pins.

**Which events the first and last bit are.** Pin-to-pin here is **first bit in** (the start block's first bit on the receive pin) to **first bit out** (the order's start block's first bit on the transmit pin): FIFO. The order depends on the price,
which is **complete in MAC word 7 (bytes 56 to 63)** (`rtl/trade64.sv` header); from `docs/bench_feed_v1.md` offsets (14 Ethernet + 20 IPv4 + 8 UDP + 8 packet header + 4 into the message) its last byte is
frame byte 57 counted from the destination address, so the last bit the decision needs arrives 66 bytes after the first bit of the preamble (8 preamble bytes + 58): at 10.3125 Gb/s with 64B/66B, 66 x 8 x 66/64 x 96.97 ps = **52.8 ns**. (Derived here; the whole 78-byte feed frame with preamble and FCS is 62.4 ns.)

**Early start.** The `lat_agent_both` and `lat_all3` builds start the order's MAC preamble before the decision is final (the frame's FCS verdict comes later and an order that should not go leaves with a wrong FCS; designs/b96_kr260_10g `trade64.sv` header, `results/b97/README.md`).
So their D (8 and 6 clocks) is shorter than the time the price needs to arrive. STAC-T0 results are for a defined test; whether a design may start the frame before the index is complete is a question for its rules: **UNCONFIRMED**.

### Recorded numbers (medians of 100 restarts; clocks of 6.2058 ns; E is the median of per-link minima)

| Build | E | L | D = L - 2E | L - E | Tick-to-trade (L - E - 0.83 ns) | File |
|---|---|---|---|---|---|---|
| `lat_all3` (97C) | 20 (124.1 ns) | 46 | 6 (37.2 ns) | 26 | **160.5 ns** (briefings say about 161) | `results/b97c/hw/20261118_194221/all3/stage3.json` |
| `lat_agent_both` (97C) | 20 | 48 | 8 | 28 | 172.9 ns | `.../agent_both/stage3.json` |
| default `control` (97C, `RATE_MATCH = 0`) | 20 | 50 | 10 | 30 | 185.3 ns | `.../control/stage3.json`, `results/b96/hw/20261117_101326/stage3.json` |
| 96C buffer (`RATE_MATCH = 1`, macro FIFO) | 24.5 | 61 | 12 | 36.5 | 226 ns (design.md) | `results/b96c/hw/20261119_080724/control/stage3.json` |
| 96E `rm_gp` (own buffer) | 21 (per-link maxima median 22) | 54 | 12 | 33 | 204.0 ns (E 21; 201 ns with E 21.5) | `results/b96e/hw/20261119_231251/rm_gp/stage3.json` |

Uncertainty: the counter is 1 clock (6.2 ns); E and L are quoted as the median of per-link minima; design.md section 6 states +/- 1 clock. D = L - 2E moves by 2 for a half-clock of E, so D's split from E is soft (96E report).

Simulation (zero-latency GT stand-in, mean over four phases, `results/b96e/core_lat_sim.json`): digital tick-to-trade 10.6 clocks (price word in to order start block out), receive-start stamp path S 5.6 (transmit stamp to receive stamp), D 10.4, for the default `RATE_MATCH = 0` path.

### What the predictions (96F, 96F1) claim, and their status

Not measured on a board (96F1's board run is pre-registered, not run): bypassing both GT buffers lowers E by 2.9 to 4.5 clocks (18 to 28 ns), tick-to-trade for `rm_gp` from about 205 ns to 177 to 187 ns; loop-timed transmit adds 3 to 4 clocks of fabric crossing saving:
`lat_all3` 161 ns to 115 to 125 ns (V1) or 121 to 131 ns (V2) (`results/b96f/latency_prediction.json`, `reports/96F_loop_timing_feasibility_report.md`). The GT part rests on third-party GTY figures (TX 7.7 to 10.9 ns, RX 13.2 to 17.1 ns): **UNCONFIRMED for this GTH**.

Update (brief 126, 2026-11-21): the bypass was then measured on a board (96F1b, `results/b96f1/hw/20261120_215255/rm_gp_bypass`: E 21.0 to 17.0 clocks, D unchanged), and the two measured improvements are combined in build `lat_all3_bypass`, whose board test is pre-registered at E 16.0, L 38.0, D 6.0, L - E 22 clocks (about 135.7 ns) and not yet run: `results/b126/README.md`, `results/b126/preregistration.md`. The definitions above are unchanged.

## 2. Industry definitions

### STAC-T0 (primary: STAC-T0 Overview, 5 November 2020)

- STAC-T0 "evaluates the tick-to-trade network-I/O latency of any trading platform", treating the stack under test (SUT) as a black box that interacts "solely via network packets, which it timestamps in hardware".
  A hardware replay sends UDP market data; the SUT replies with a TCP order. "Ingress and egress messages are timestamped on the wire."
- The SUT reads a **uint64 index** at a fixed position in each packet; if the index is a multiple of 1024 it sends a **118-byte TCP frame** (all headers and FCS) containing the index. Two streams: 507-byte frames (structure A) and **68-byte** frames (B), at LOWRATE (one packet per ms), MEDRATE (1 Gb/s) and HIGHRATE.
- Timestamps: tFI first bit of the ingress frame; **tIND last bit of the index**; tLI last bit of the ingress frame; tFO **first bit of the egress packet**; tLO last bit of the egress packet. Only one ingress and one egress timestamp is observed by the capture equipment; the rest are inferred using the serialisation delay, "taking into account 64b/66b encoding, differing offsets based on start-of-frame types".
- Metrics: **ACTIONABLE = tFO - tIND**; FILO = tLO - tFI; LIFO = tFO - tLI; FIFO = tFO - tFI. Actionable latency is "the latency that is under the control of the SUT, if we do not consider cables to be part of the SUT"; the other three "include some serialization delay".
- A STAC report for another STAC-T0 result gives the test harness an uncertainty of +/- 2 ns (secondary: search-result summary of the Exablaze report, node 44755; page not fetched; **UNCONFIRMED**).

### The 13.9 ns result

- STAC report for **Exegy nxFramework and nxTCP-UDP-10g-ULL IP core on an AMD Alveo UL3524, in a Dell PowerEdge R7525 with AMD EPYC 7313 CPUs** (read from docs.stacresearch.com/node/48577): actionable latency **minimum 13.9 ns for the 507-byte frames, 14.1 ns for the 68-byte frames**;
  reported as 40 to 42 % and 43 to 49 % below the prior record (SUT XLX200514, **24.2 ns** for 68-byte frames, a 2020 AMD/LDA STAC-T0 report; secondary, from a search summary of node 45733, page not fetched). The page gives no median or maximum and no harness description in the text read (**UNCONFIRMED**: maxima, the tap, uncertainty).
  Dated 25 June 2024 on the page read; Exegy's release 27 June 2024.
- Exegy's description: "an off-the-shelf solution with an asynchronous implementation for the critical path of the algorithm and network stack"; jitter reduced "to 200 picoseconds". The transceiver, its mode, the FPGA part and the clocking are **not stated** in what was read.
  Vendor press, not independent.
- The UL3524 uses GTF transceivers. AMD's launch release (27 September 2023) claims "less than 3 ns FPGA transceiver latency" and a 7x improvement; footnote 2 says "based on simulation comparison between Virtex UltraScale+ GTY transceivers and ultra-low latency GTF transceivers"; footnote 1's
  measurement is a **near-end loopback of the GTF itself in RAW mode** (TX data latched to RX data back in the fabric; "does not include protocol overhead, protocol framing, programmable logic (PL) latency"). AMD's GitHub benchmark page reports a measured **2.34 ns (RAW) and 5.44 ns (MAC)** for that TX-plus-RX loopback, at about 644 MHz clocks.
  It is a transceiver-only figure with no optics, no fibre and no logic: **not a tick-to-trade figure**, and neither AMD page uses the words tick-to-trade or wire-to-wire.

### "Wire-to-wire" and "tick-to-trade" in common use

- Wire-to-wire: "the time between a trading system receiving an inbound message and subsequently sending an outbound message"; tick-to-trade (tick-to-order) is the case where the inbound is a market-data message and the outbound an order. The boundary varies: whether timestamps are at start of frame or end of frame, and "not all vendors apply these consistently" (secondary: Databento glossary).
- Exegy: tick-to-trade is "the time it takes for an order to be sent to the exchange in response to a market data update", and it calls STAC-T0 a tick-to-trade network-I/O benchmark. Search summaries of other pages describe a hardware-level version as last bit in at the cage to first bit out at the cage (**UNCONFIRMED**, secondary).
- Vendor sources on the owner's list (Orthogone's MAC/PCS figures, Design Gateway, Algo-Logic) were not read for this note; their figures are not used.

## 3. The mapping: from our L - E to a STAC-T0-like figure

All for `lat_all3` (board, 97C). Times in ns, clocks of 6.2058 ns. "Ours?" says how well we know the value.

| Step | Value | Ours? |
|---|---|---|
| L - E (board, medians) | 26 clocks = 161.35 ns | **measured** (stamps inside the FPGA, 1 clock resolution) |
| Minus the fibre (0.17 m) | -0.83 ns, gives **160.5 ns** | measured fibre length x 4.9 ns/m |
| Minus the module's own delay | unknown, not subtracted; so 160.5 is an upper bound on pin-to-pin FIFO | **cannot know** from this record |
| = **FIFO-like** (first bit in to first bit out at the transceiver pins) | **at most 160.5 ns** | derived |
| Minus the frame time to the last index bit: 66 bytes with preamble at 66/64 | -52.8 ns, gives **at most 107.7 ns** | derived from the frame layout; the first-bit pin time of the real STAC frame layout differs (**UNCONFIRMED**) |
| = **ACTIONABLE-like** (tFO - tIND) | **at most about 108 ns** | derived |
| Alternatively minus the whole feed frame (70 + 8 bytes, 62.4 ns) | **LIFO-like at most 98.1 ns** | derived |

Which components make up the actionable-like 108 ns, again for `lat_all3`:

| Component | Value | Status |
|---|---|---|
| GT transmit + GT receive + module + fibre (E minus the digital stamp path S: 124.1 - 34.8) | **about 89 ns** (72 % of E) | derived: E measured, S from xsim with a GT stand-in; **not separable** into GT, optics, fibre. The briefings' "about 93 ns" is the same quantity with a different S. |
| of which fibre | 0.83 ns | measured length |
| of which GT buffers and PMA (both GTs) | 21 to 28 ns if third-party GTY figures held (TX 7.7 to 10.9, RX 13.2 to 17.1) | **UNCONFIRMED for this GTH**; if right, the module and the rest of E would be about 60 ns, which is larger than expected for an SFP+ and is itself **unexplained**: a measurement of E in near-end PMA loopback (variant a exists; no board record of its E) would split GT from module |
| Our PCS, MAC, crossing, decision, order build (digital): S + D minus the 52.8 ns frame time | S 34.8 + D 37.2 - 52.8 = **about 19 ns** (3.1 clocks) | derived; the stamp-based accounting and the simulated price-word-to-start-block figure (10.6 clocks) disagree by 2 to 3 clocks (16 ns): see below |
| Sum (89 - 0.83 of module+fibre excluded as above, +19) | about 108 ns | consistent with the row above by construction |

**The simulation and board accountings disagree by 2 to 3 clocks.** Simulation (97C, default): S + D = 5.6 + 10.4 = 16.0 clocks of digital frame-start to order-start; simulated price-word to start-block = 10.6; the difference, 5.4, should equal the frame start to the price word's arrival,
which the layout gives as 8 words (start block, then MAC words 0 to 7). About 2.6 clocks are unattributed (97's `docs/latency_reduction.md` calls the same disagreement "about 4 clocks" in its own accounting). It is stated, not resolved.

### The honest like-for-like gap

| Item | Ours (`lat_all3`) | STAC-T0 13.9 ns result | Known? |
|---|---|---|---|
| Metric | derived actionable-like, **at most 108 ns**; FIFO 160.5 ns | actionable, **minimum** over the run: 13.9 ns (507 B), 14.1 ns (68 B) | definitions known; ours derived |
| Measured by | counter in the FPGA, 6.2 ns resolution, +/- 1 clock; median of 100 per-link minima | hardware wire timestamps (the harness); uncertainty of the harness **UNCONFIRMED** for this report (+/- 2 ns in another report) | |
| Where the "wire" is | transceiver pins, with the module and 0.17 m of fibre inside | the SUT's network port; cables excluded from the SUT; whether the SUT included optics or a DAC **not stated** | **cannot know** |
| Transceiver | GTH, 64-bit RAW, **both GT buffers on**, user clock 161 MHz, our own 64B/66B PCS in fabric (2 clocks in, 2 out) | GTF on the UL3524, mode **not stated**; transceiver loopback alone is 2.34 ns RAW, 5.44 ns MAC (AMD) | theirs **cannot know** |
| MAC and protocol logic | own 64-bit MAC and PCS, one UDP rule; no TCP | nxTCP-UDP-10g-ULL core, TCP order; the logic style "asynchronous" per Exegy | theirs **cannot know** |
| Decision | one compare on a price; early MAC start before the decision (speculative) | index mod 1024 | whether early start is allowed in STAC-T0: **UNCONFIRMED** |
| Clocking | 161 MHz synchronous, 6.2 ns per register; crossing of 3 to 4 clocks between the recovered and transmit clocks | **not stated** | |
| Frames | feed 70 B + preamble; order 66 + FCS = 70 B, UDP | 68 B or 507 B in; 118 B TCP out | |

Reading: of our derived actionable-like 108 ns, the transceiver, optics and fibre (not separable) are about 89 ns, 80 % to 85 %. If the GT buffers are bypassed (96F1, predicted 18 to 28 ns less, **board run pending**) and the fabric crossing removed by loop timing (96F, 3 to 4 clocks, **not built**), the predicted `lat_all3` FIFO becomes 115 to 125 ns (V1) and the actionable-like figure about 62 to 72 ns (115 - 52.8 to 125 - 52.8; derived here, depends on the UNCONFIRMED GT figures).
**Even if every transceiver item were removed, our digital path alone (about 19 ns, +/- 16 ns for the unresolved accounting) would not be below 13.9 ns by a margin we could demonstrate.** The 13.9 ns result is about a different class of design: an asynchronous critical path and a transceiver measured in single nanoseconds.
The 96F1 bypass and the loop timing move our number towards it by tens of nanoseconds; they do not close it.

## 4. What later briefs must measure to be comparable

1. Count the order's first bit and the index's last bit, not stamp points inside the MAC: an ILA or a second board or a capture device on the wire (resolution under 1 clock).
2. E in near-end PMA loopback and in far-end loopback on the same build, to separate GT, module and fibre.
3. Report the minimum and the median and say which; keep the +/- 1 clock beside it.
4. State whether the early MAC start is on.
5. Use a frame layout whose index is the last field, or quote tFO - tIND from the frame layout as done here.

## 5. What to say in an interview

"On the KR260 I measure first-bit-in to first-bit-out at the transceiver pins, from counters in the FPGA with 6 ns resolution: about 160 ns for my fastest build, optics and a 17 cm fibre included. In STAC-T0's terms that is a FIFO latency;
their 13.9 ns record is an actionable latency, from the last bit the decision needs, on a card with a 3 ns-class transceiver, so my comparable figure is nearer 100 ns, most of it the transceiver path rather than the logic. I am not claiming parity: they time on the wire with an external harness and I can't resolve 14 ns.
What I can claim is that I know where each of my 26 clocks goes, that bypassing the GT buffers is predicted to save 20 to 30 ns and is the next measurement, and what I'd have to measure to compare properly."

## 6. Proposed replacement for the interview briefing's "What not to claim" line

"Never compare our 161 ns (L - E - fibre: first bit in to first bit out at the SFP+ pins, FPGA stamps, 6.2 ns resolution, optics included, GTH with GT buffers on, `lat_all3`) with STAC-T0's 13.9 ns, which is an *actionable* latency (last index bit to first order bit, wire timestamps, minimum, Alveo UL3524/Exegy) without
saying so. Our like-for-like figure is derived, about 108 ns, and mostly transceiver path. Never claim parity, and never call 161 ns 'inside the design': it includes the transceiver and optics." (`docs/latency_definitions.md`)

## Sources (all read 2026-11-20; "UNCONFIRMED" where the page itself was not read)

| Source | URL | Used for |
|---|---|---|
| STAC-T0 Overview, 5 Nov 2020 (PDF, text extracted) | https://docs.stacresearch.com/system/files/central/STAC-T0%20backgrounder.pdf | tFI, tIND, tLI, tFO, tLO; the four metrics; black-box and wire-timestamp method; 118 B and 68 B / 507 B frames; "cables not part of the SUT" |
| STAC report: Exegy / AMD STAC-T0 (page read through a summariser: node 48577) | https://docs.stacresearch.com/node/48577 | SUT description; 13.9 ns (507 B), 14.1 ns (68 B); actionable definition; prior record comparisons; date |
| Exegy release, 27 June 2024 | https://www.exegy.com/exegy-amd-new-record/ | "asynchronous implementation", 200 ps jitter, tick-to-trade wording |
| FISD article, 11 July 2024 | https://fisd.net/?p=115240 | same claims, secondary |
| AMD Alveo UL3524 launch release, 27 Sep 2023 | https://ir.amd.com/news-events/press-releases/detail/1158/amd-unveils-purpose-built-fpga-based-accelerator-for | "less than 3 ns" transceiver latency and its footnotes |
| AMD UL3524 GTF latency page (Alveo-Cards) | https://xilinx.github.io/Alveo-Cards/cards/ul3524/build/html/docs/GTF_Latency/README.html | 2.34 ns RAW, 5.44 ns MAC; near-end loopback method |
| Databento glossary, wire-to-wire latency | https://databento.com/microstructure/wire-to-wire-latency | common usage; secondary |
| AMD blog on the record (page fetch timed out; only a search summary) | https://www.amd.com/en/blogs/2024/amd-sets-stac-benchmark-world-record-for-fastest-e.html (did not load from this machine at check time) | **UNCONFIRMED**: server and capture equipment named in the summary not used |
| STAC node 45733 (2020 LDA/Xilinx, 24.2 ns) and node 44755 (Exablaze, harness uncertainty) | https://docs.stacresearch.com/node/45733, https://docs.stacresearch.com/node/44755 | **UNCONFIRMED**: search summaries only, pages not read |
