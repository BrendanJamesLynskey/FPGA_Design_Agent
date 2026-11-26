# Results of brief 241: data movement and DMA

Records of the simulation, formal, seeded-fault and out-of-context Vivado runs of the library entry `ip_lib/sg_dma` (a scatter-gather DMA engine), made on
2026-11-26, and of the comparison with a behavioural model of AMD's AXI DMA. The board run and the agent run are pre-registered in
[docs/241_dma_prereg.md](../../docs/241_dma_prereg.md) and **not run**. Every number below is read from a file in this folder.

## Records

| File | What it holds |
|---|---|
| `sim_measure.jsonl` | one line per simulated point (engine configuration, descriptor size, one or six descriptors): clocks from the `HEAD` write to the first descriptor fetch, the first and last data beat, the last status response (cocotb, Icarus Verilog 14, memory model with read latency 20 and write-response latency 15 clocks, no random gaps; `tools/dma_measure.py run`) |
| `summary.json` | the same points with the derived fractions of the port limit, and the like-for-like point against AMD's published figures (`tools/dma_measure.py plot`) |
| `throughput_vs_size.svg`, `latency_overhead.svg` | the two plots drawn from `summary.json` |
| `faults.json` | the 22 seeded faults of the engine and whether the bench caught each (`flow/net/faults.py`) |
| `formal.json` | the SymbiYosys tasks and the five faults that also name formal tasks (`ip_lib/sg_dma/formal/run_formal.py`) |
| `ooc.json` | out-of-context Vivado 2026.1 synthesis, placement and routing of six configurations on two parts (`python -m flow.ipchar sg_dma`, one record per part under `ip_lib/sg_dma/char/`) |

## Throughput and latency (simulation, not a board)

The engine's own limit with a fixed-latency memory and an always-ready stream: the first table is the fraction of the memory port's limit over six descriptors of the same size back to back (descriptors included), the second the clocks from the `HEAD` write to the status response of one descriptor, the third the like-for-like point against PG021's published figures. The memory has no refresh and no other masters.

| Configuration | 64 B | 256 B | 1024 B | 4096 B | 16384 B |
|---|---|---|---|---|---|
| MM2S, 32-bit, burst 4, 4 outstanding | 0.200 | 0.422 | 0.582 | 0.643 | 0.661 |
| MM2S, 32-bit, burst 16, 1 outstanding | 0.200 | 0.341 | 0.413 | 0.436 | 0.442 |
| MM2S, 32-bit, burst 16, 4 outstanding | 0.200 | 0.501 | 0.800 | 0.941 | 0.985 |
| MM2S, 64-bit, burst 16, 4 outstanding | 0.115 | 0.341 | 0.674 | 0.892 | 0.971 |
| S2MM, 32-bit, burst 16, 4 outstanding | 0.211 | 0.517 | 0.811 | 0.945 | 0.986 |

| Configuration | 64 B | 256 B | 1024 B | 4096 B | 16384 B |
|---|---|---|---|---|---|
| MM2S, 32-bit, burst 4, 4 outstanding | 79 | 151 | 439 | 1591 | 6199 |
| MM2S, 32-bit, burst 16, 1 outstanding | 79 | 187 | 619 | 2347 | 9259 |
| MM2S, 32-bit, burst 16, 4 outstanding | 79 | 127 | 319 | 1087 | 4159 |
| MM2S, 64-bit, burst 16, 4 outstanding | 69 | 93 | 189 | 573 | 2109 |
| S2MM, 32-bit, burst 16, 4 outstanding | 75 | 123 | 315 | 1083 | 4155 |

| Direction | clocks, first data address to last beat | MB/s at 100 MHz | AMD AXI DMA, PG021 table 2 (MB/s) | start-up, AMD model | start-up, ours |
|---|---|---|---|---|---|
| MM2S, 10000 bytes | 2520 | 396.83 | 399.04 | 44 | 46 |
| S2MM, 10000 bytes | 2501 | 399.84 | 298.59 | 39 | 27 |

Reading: each descriptor costs about 64 clocks beyond its data in this memory (a descriptor fetch round trip, the first data round trip and the status-write round trip, one after another), so 64 bytes reach 0.2 of the port and 16 KB reach 0.985. One burst in flight with 20 clocks of read latency settles at 0.44, as 16 beats over (16 + 20) clocks predicts; four in flight hide the latency. A 64-bit port needs bigger transfers to reach the same fraction, since the descriptor overhead is the same number of clocks over fewer beats.

### Against AMD's AXI DMA, and what that comparison is

`ip_lib/sg_dma/amd_axi_dma_model.py` is our behavioural model of the AXI DMA built **only** from PG021 v7.1 (2025-06-24). Conformance of the model, by row:

| Behaviour | Source | Status |
|---|---|---|
| MM2S: 10, 28 and 6 clocks from a tail-descriptor write to the first stream beat | PG021 table 1 | documented (AMD's test bench, memory latency not stated) |
| S2MM: 39 clocks from the first stream beat to the first write address | PG021 table 1 | documented |
| MM2S 399.04 MB/s for 10,000 bytes at 100 MHz, 32-bit | PG021 table 2 | documented; reproduced by the model exactly (2,506 clocks) |
| S2MM 298.59 MB/s for the same | PG021 table 2 | documented; reproduced by fitting one gap |
| S2MM gap of about 5.2 clocks between 16-beat bursts | derived from table 2 | **inferred**, fitted to that one figure |
| Descriptor 16 words, 64-byte aligned, 13 words used | PG021 table 25 | documented |
| Behaviour outside 32-bit, burst 16, one channel active, default configuration | - | not modelled: the functions raise an error |

The vendor core was **not** run (no simulation or board run of it in this brief). The guide does not state the latency of its test bench's memory, so
the S2MM gap may belong to that memory and not to the core; our engine reaching the port limit in both directions in a memory that accepts write data at full rate says nothing about the vendor core in the same memory. The model is useful as the documented numbers in one place with a stated envelope, not as a prediction.

## Seeded faults

22 faults, each one string replaced in a copy of the RTL, run against `test_engine` at the points that reach it: `faults.json` has the status of each. The faults the formal tasks also refute:

| Fault | Tasks | Result |
|---|---|---|
| `no_4k_split` | m32 FAIL, s32 FAIL | refuted |
| `wlast_early` | g32s FAIL | refuted |
| `outstanding_one_over` | g32m FAIL, g32s FAIL | refuted |
| `w_before_aw` | g32s FAIL | refuted |
| `status_w_before_aw` | g32m FAIL | refuted |

## Formal

| Task | Kind | Status | Seconds |
|---|---|---|---|
| `m32` | k-induction | PASS | 1.9 |
| `s32` | k-induction | PASS | 1.9 |
| `m64` | k-induction | PASS | 2.5 |
| `s64` | k-induction | PASS | 2.7 |
| `m128` | k-induction | PASS | 2.7 |
| `s128` | k-induction | PASS | 3.1 |
| `g32m` | bounded (bmc depth 30) | PASS | 112.2 |
| `g32s` | bounded (bmc depth 30) | PASS | 457.3 |
| `m32c` | cover | PASS | 2.4 |
| `s32c` | cover | PASS | 3.5 |

The k-induction proofs cover the hold rules on every channel the engine drives, burst size and type, alignment and the 4 KB rule, for every descriptor the engine could read (the memory returns arbitrary words) at 32, 64 and 128 bits in both directions. The bounded proofs (depth 30) cover write data after its address, `wlast`, and the outstanding limit; they are bounded because their bookkeeping is in the harness and not tied to the engine's counters, so k-induction cannot close them. The proofs were useful: they found (1) that a ring base that is not 16-byte aligned can make a descriptor fetch cross a page (RING_LO bits 3:0 now read 0), (2) that a change to the ring registers during a fetch could change an address already offered (the descriptor address is now latched), and (3) a counter that could wrap on an unsolicited response (the engine now accepts a response or read data only for a burst it addressed). The simulation found a fourth: after a failed descriptor fetch the rest of the burst stayed in the memory's read channel (the engine now reads and discards it).

## Out-of-context cost

Vivado 2026.1, out of context (no I/O constraints, clock 4.0 ns on `aclk`), synthesis, placement and routing, one run per point, `MAX_BURST` 16, `OUTSTANDING` 4, `ADDR_W` 32. The Fmax estimate is 1000 / (4.0 - WNS) capped as `flow/fmax_cap.py` says; with a clock this far below what the part allows, treat it as the slack at 4 ns, not the limit of the design. Power is vectorless (default toggle rates), not a measurement.

| Part | Direction | Data width | LUTs | Flip-flops | Block RAM tiles | DSP | WNS at 4.0 ns (ns) | Fmax estimate (MHz) | Fmax limited by | Vectorless power (W) |
|---|---|---|---|---|---|---|---|---|---|---|
| xc7z020clg484-1 | MM2S | 32 | 616 | 503 | 0 | 0 | -6.127 | 98.7 | setup slack at the target clock | 0.123 |
| xc7z020clg484-1 | S2MM | 32 | 592 | 504 | 0 | 0 | -5.686 | 103.2 | setup slack at the target clock | 0.123 |
| xc7z020clg484-1 | MM2S | 64 | 627 | 450 | 0 | 0 | -6.865 | 92.0 | setup slack at the target clock | 0.122 |
| xc7z020clg484-1 | S2MM | 64 | 613 | 453 | 0 | 0 | -6.195 | 98.1 | setup slack at the target clock | 0.122 |
| xc7z020clg484-1 | MM2S | 128 | 640 | 439 | 0 | 0 | -5.688 | 103.2 | setup slack at the target clock | 0.116 |
| xc7z020clg484-1 | S2MM | 128 | 621 | 442 | 0 | 0 | -5.757 | 102.5 | setup slack at the target clock | 0.12 |
| xck26-sfvc784-2LV-c | MM2S | 32 | 571 | 501 | 0 | 0 | 0.492 | 285.1 | setup slack at the target clock | 0.294 |
| xck26-sfvc784-2LV-c | S2MM | 32 | 566 | 504 | 0 | 0 | 0.504 | 286.0 | setup slack at the target clock | 0.295 |
| xck26-sfvc784-2LV-c | MM2S | 64 | 601 | 450 | 0 | 0 | 0.602 | 294.3 | setup slack at the target clock | 0.294 |
| xck26-sfvc784-2LV-c | S2MM | 64 | 578 | 452 | 0 | 0 | 0.661 | 299.5 | setup slack at the target clock | 0.295 |
| xck26-sfvc784-2LV-c | MM2S | 128 | 588 | 439 | 0 | 0 | 0.638 | 297.4 | setup slack at the target clock | 0.294 |
| xck26-sfvc784-2LV-c | S2MM | 128 | 583 | 442 | 0 | 0 | 0.696 | 302.7 | setup slack at the target clock | 0.295 |

Reading: the engine is a few hundred LUTs, with no block RAM and no DSP, on both parts; the flip-flop count falls a little as the data width grows (501 to 439 on `xck26`; the cause was not investigated). Timing is the weak side. On `xc7z020clg484-1` (speed grade -1) the 4.0 ns target is missed by about 6 ns, so the engine runs near 100 MHz there; on `xck26` it meets 4.0 ns with 0.5 to 0.7 ns to spare, so its limit is above 285 MHz and was not found (the clock was not pushed). The worst path on the `xc7z020` MM2S 32-bit run (`build/ipchar/.../timing_worst_setup.rpt`, not committed) goes from `d_addr` through the burst-length function (`nbeats`: a 4 KB distance, the remaining bytes and the burst limit, compared in a chain of carries), then the beat-counter compare, to the clock enable of `d_addr`: 14 logic levels, 9.8 ns. Computing the burst length once per burst and registering it would shorten it; that is a follow-up, listed in the entry's gaps, and not done here because it would restart the proofs and the fault runs.

## Reproduce

```
export PATH=$HOME/.local/opt/oss-cad-suite/bin:$PATH          # Icarus Verilog 14, SymbiYosys, slang (the OSS CAD Suite the repository pins)
python3 tools/dma_measure.py run && python3 tools/dma_measure.py like      # sim_measure.jsonl (about 40 minutes of simulation, no heavy slot)
python3 tools/dma_measure.py plot                                          # summary.json and the two plots (needs matplotlib)
python3 flow/net/faults.py --only <the names in ip_lib/sg_dma/faults.yaml> --json results/241_dma/faults.json
python3 ip_lib/sg_dma/formal/run_formal.py --json results/241_dma/formal.json
python3 -m flow.ipchar sg_dma --part xck26-sfvc784-2LV-c; python3 -m flow.ipchar sg_dma --part xc7z020clg484-1    # Vivado 2026.1, one heavy slot, about 45 minutes per part
```

The board run and the agent run cannot be regenerated from here: they have not been made (see [docs/241_dma_prereg.md](../../docs/241_dma_prereg.md)).

## Known gaps and limits

- Simulation only: one memory model of ours with fixed latency, no refresh and no other masters; the board will differ, and the tail of the latency distribution is not modelled.
- Each point is one run of a deterministic simulation; there is no spread to report. The random back-pressure runs are in the bench, not in the measurements.
- AMD's AXI DMA was not run; the model of it holds the guide's published numbers and one inferred gap, and its test bench's memory is not stated. The comparison is therefore a reading of two different set-ups.
- Vivado figures are single out-of-context runs at a 4.0 ns target; the Fmax on `xck26` is a lower bound, and the `xc7z020` figure is limited by an internal path the entry lists as a follow-up.
- The bounded proofs (depth 30) say nothing beyond that depth; there is no formal rigour sidecar for the proofs yet.
- No DMA agent run exists yet, so nothing here shows that the agent chooses or wires the engine correctly.

## Course impact

None: the course has no DMA lesson yet. A lesson on descriptors, the 4 KB rule and the cache contract is a follow-up for the planner (`FPGA_Design_Course/lessons`, Part 17 or a new part).
