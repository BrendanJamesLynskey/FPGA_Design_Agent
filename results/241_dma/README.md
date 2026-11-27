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
| `faults.json` | the 23 seeded faults of the engine and whether the bench caught each (`flow/net/faults.py`) |
| `formal.json` | the SymbiYosys tasks and the five faults that also name formal tasks (`ip_lib/sg_dma/formal/run_formal.py`) |
| `sweep_xck26_2p5ns.json` | the same six configurations on `xck26` with a 2.5 ns clock (one sweep step; `flow.ipchar --clock-ns 2.5`) |
| `before/` | `summary_before.json` and `ooc_before.json`: the records of the first version of the engine (burst length computed in the data path), kept for the before-and-after tables |
| `ooc.json` | out-of-context Vivado 2026.1 synthesis, placement and routing of six configurations on two parts (`python -m flow.ipchar sg_dma`, one record per part under `ip_lib/sg_dma/char/`) |

## Throughput and latency (simulation, not a board)

The engine's own limit with a fixed-latency memory and an always-ready stream: the first table is the fraction of the memory port's limit over six descriptors of the same size back to back (descriptors included), the second the clocks from the `HEAD` write to the status response of one descriptor, the third the like-for-like point against PG021's published figures. The memory has no refresh and no other masters.

| Configuration | 64 B | 256 B | 1024 B | 4096 B | 16384 B |
|---|---|---|---|---|---|
| MM2S, 32-bit, burst 4, 4 outstanding | 0.198 | 0.419 | 0.581 | 0.643 | 0.661 |
| MM2S, 32-bit, burst 16, 1 outstanding | 0.198 | 0.339 | 0.412 | 0.436 | 0.442 |
| MM2S, 32-bit, burst 16, 4 outstanding | 0.198 | 0.497 | 0.798 | 0.940 | 0.984 |
| MM2S, 64-bit, burst 16, 4 outstanding | 0.113 | 0.337 | 0.671 | 0.891 | 0.970 |
| S2MM, 32-bit, burst 16, 4 outstanding | 0.208 | 0.513 | 0.808 | 0.944 | 0.985 |

| Configuration | 64 B | 256 B | 1024 B | 4096 B | 16384 B |
|---|---|---|---|---|---|
| MM2S, 32-bit, burst 4, 4 outstanding | 80 | 152 | 440 | 1592 | 6200 |
| MM2S, 32-bit, burst 16, 1 outstanding | 80 | 188 | 620 | 2348 | 9260 |
| MM2S, 32-bit, burst 16, 4 outstanding | 80 | 128 | 320 | 1088 | 4160 |
| MM2S, 64-bit, burst 16, 4 outstanding | 70 | 94 | 190 | 574 | 2110 |
| S2MM, 32-bit, burst 16, 4 outstanding | 76 | 124 | 316 | 1084 | 4156 |

| Direction | clocks, first data address to last beat | MB/s at 100 MHz | AMD AXI DMA, PG021 table 2 (MB/s) | start-up, AMD model | start-up, ours |
|---|---|---|---|---|---|
| MM2S, 10000 bytes | 2520 | 396.83 | 399.04 | 44 | 47 |
| S2MM, 10000 bytes | 2501 | 399.84 | 298.59 | 39 | 28 |
| MM2S, 10000 bytes | 2520 | 396.83 | 399.04 | 44 | 47 |
| S2MM, 10000 bytes | 2501 | 399.84 | 298.59 | 39 | 28 |

Reading: each descriptor costs about 65 clocks beyond its data in this memory (a descriptor fetch round trip, the first data round trip and the status-write round trip, one after another, with a clock or two for the registered burst length), so 64 bytes reach 0.2 of the port and 16 KB reach 0.985. One burst in flight with 20 clocks of read latency settles at 0.44, as 16 beats over (16 + 20) clocks predicts; four in flight hide the latency. A 64-bit port needs bigger transfers to reach the same fraction, since the descriptor overhead is the same number of clocks over fewer beats.

### Before and after registering the burst length (2026-11-27)

The first version computed each burst's length (`nbeats`) in the path to the data-side counters. This version registers it once per burst (`a_n`, valid one clock after the address changes) and keeps the lengths of bursts in flight in a small queue the data side reads, so the data side holds no address or remaining-byte counters. The cost is one clock per burst on the address side and about six clocks per six descriptors (one per descriptor) in these runs; the data side is unchanged. Earlier records: `before/summary_before.json`, `before/ooc_before.json`.

| Configuration | Size (bytes) | Six descriptors, clocks before | after | Fraction of port before | after |
|---|---|---|---|---|---|
| MM2S, 32-bit, burst 16, 4 outstanding | 64 | 479 | 485 | 0.200 | 0.198 |
| MM2S, 32-bit, burst 16, 4 outstanding | 4096 | 6527 | 6533 | 0.941 | 0.940 |
| MM2S, 32-bit, burst 16, 4 outstanding | 16384 | 24959 | 24965 | 0.985 | 0.984 |
| S2MM, 32-bit, burst 16, 4 outstanding | 64 | 455 | 461 | 0.211 | 0.208 |
| S2MM, 32-bit, burst 16, 4 outstanding | 4096 | 6503 | 6509 | 0.945 | 0.944 |
| S2MM, 32-bit, burst 16, 4 outstanding | 16384 | 24935 | 24941 | 0.986 | 0.985 |
| MM2S, 64-bit, burst 16, 4 outstanding | 64 | 419 | 425 | 0.115 | 0.113 |
| MM2S, 64-bit, burst 16, 4 outstanding | 4096 | 3443 | 3449 | 0.892 | 0.891 |
| MM2S, 64-bit, burst 16, 4 outstanding | 16384 | 12659 | 12665 | 0.971 | 0.970 |
| MM2S, 32-bit, burst 16, 1 outstanding | 64 | 479 | 485 | 0.200 | 0.198 |
| MM2S, 32-bit, burst 16, 1 outstanding | 4096 | 14087 | 14093 | 0.436 | 0.436 |
| MM2S, 32-bit, burst 16, 1 outstanding | 16384 | 55559 | 55565 | 0.442 | 0.442 |

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

23 faults, each one string replaced in a copy of the RTL, run against `test_engine` at the points that reach it: `faults.json` has the status of each. The faults the formal tasks also refute:

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
| `m32` | k-induction | PASS | 4.2 |
| `s32` | k-induction | PASS | 4.3 |
| `m64` | k-induction | PASS | 5.6 |
| `s64` | k-induction | PASS | 5.1 |
| `m128` | k-induction | PASS | 5.9 |
| `s128` | k-induction | PASS | 8.0 |
| `g32m` | bounded (bmc depth 30) | PASS | 28.2 |
| `g32s` | bounded (bmc depth 30) | PASS | 28.8 |
| `m32c` | cover | PASS | 7.1 |
| `s32c` | cover | PASS | 8.0 |
| `g32mc` | cover | PASS | 9.0 |
| `g32sc` | cover | PASS | 7.5 |

The k-induction proofs cover the hold rules on every channel the engine drives, burst size and type, alignment and the 4 KB rule, for every descriptor the engine could read (the memory returns arbitrary words) at 32, 64 and 128 bits in both directions. The proofs now hold for 24 assertions (4 bounded). The bounded proofs (depth 30) cover write data after its address, `wlast`, and the outstanding limit; they are bounded because their bookkeeping is in the harness and not tied to the engine's counters, so k-induction cannot close them. The proofs were useful: they found (1) that a ring base that is not 16-byte aligned can make a descriptor fetch cross a page (RING_LO bits 3:0 now read 0), (2) that a change to the ring registers during a fetch could change an address already offered (the descriptor address is now latched), and (3) a counter that could wrap on an unsolicited response (the engine now accepts a response or read data only for a burst it addressed). The simulation found a fourth: after a failed descriptor fetch the rest of the burst stayed in the memory's read channel (the engine now reads and discards it).

## Out-of-context cost

Vivado 2026.1, out of context (no I/O constraints, clock on `aclk`), synthesis, placement and routing, one run per point, `MAX_BURST` 16, `OUTSTANDING` 4, `ADDR_W` 32. The Fmax estimate is 1000 / (clock - WNS), capped as `flow/fmax_cap.py` says; where WNS is positive it is a lower bound. Power is vectorless (default toggle rates), not a measurement. The column "before" is the first version of the engine.

| Part | Direction | Data width | LUTs | Flip-flops | WNS at 4.0 ns (ns) | Fmax estimate (MHz) | Fmax before the change (MHz) | Vectorless power (W) |
|---|---|---|---|---|---|---|---|---|
| xc7z020clg484-1 | MM2S | 32 | 488 | 479 | -3.194 | 139.0 | 98.7 | 0.12 |
| xc7z020clg484-1 | S2MM | 32 | 491 | 482 | -2.721 | 148.8 | 103.2 | 0.117 |
| xc7z020clg484-1 | MM2S | 64 | 503 | 426 | -2.964 | 143.6 | 92.0 | 0.118 |
| xc7z020clg484-1 | S2MM | 64 | 500 | 429 | -2.662 | 150.1 | 98.1 | 0.119 |
| xc7z020clg484-1 | MM2S | 128 | 518 | 417 | -2.835 | 146.3 | 103.2 | 0.117 |
| xc7z020clg484-1 | S2MM | 128 | 507 | 420 | -2.622 | 151.0 | 102.5 | 0.116 |
| xck26-sfvc784-2LV-c | MM2S | 32 | 476 | 479 | 1.075 | 341.9 | 285.1 | 0.294 |
| xck26-sfvc784-2LV-c | S2MM | 32 | 485 | 483 | 1.038 | 337.6 | 286.0 | 0.294 |
| xck26-sfvc784-2LV-c | MM2S | 64 | 500 | 427 | 0.878 | 320.3 | 294.3 | 0.294 |
| xck26-sfvc784-2LV-c | S2MM | 64 | 502 | 431 | 1.019 | 335.5 | 299.5 | 0.293 |
| xck26-sfvc784-2LV-c | MM2S | 128 | 508 | 417 | 1.024 | 336.0 | 297.4 | 0.294 |
| xck26-sfvc784-2LV-c | S2MM | 128 | 508 | 420 | 0.733 | 306.1 | 302.7 | 0.294 |

A second clock step on `xck26`, at 2.5 ns, meets timing at every point, so the estimate there is above 415 MHz; the step beyond it (2.0 ns) was not run because the heavy slots stayed busy, so the true limit is not found, only bounded below:

| Direction | Data width | LUTs | Flip-flops | WNS at 2.5 ns (ns) | Fmax estimate (MHz) |
|---|---|---|---|---|---|
| MM2S | 32 | 495 | 479 | 0.172 | 429.6 |
| S2MM | 32 | 498 | 482 | 0.095 | 415.8 |
| MM2S | 64 | 521 | 428 | 0.208 | 436.3 |
| S2MM | 64 | 527 | 431 | 0.143 | 424.3 |
| MM2S | 128 | 529 | 417 | 0.129 | 421.8 |
| S2MM | 128 | 528 | 420 | 0.209 | 436.5 |

Reading: the engine is under 530 LUTs with no block RAM and no DSP on both parts. Registering the burst length took the Zynq-7000 (`xc7z020`, speed grade -1) from about 100 MHz to 139 to 151 MHz; the previous worst path (14 logic levels from `d_addr` through `nbeats` to the clock enable of the data counters) is gone. The worst path now (`xc7z020` MM2S 32-bit, `build/ipchar/.../timing_worst_setup.rpt`, not committed) is the interrupt coalescing logic, `tail` to `since_irq` (the ring-wrap compare, the threshold compare and the drained test, 10 logic levels, 7.1 ns), which is outside the data path; shortening it is a follow-up, listed in the entry's gaps.

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
- Vivado figures are single out-of-context runs at a 4.0 ns target (and one 2.5 ns step on `xck26`); the Fmax on `xck26` is a lower bound, and the `xc7z020` figure is limited by the interrupt coalescing path, which the entry lists as a follow-up.
- The bounded proofs (depth 30) say nothing beyond that depth; the antecedent covers that show the assertions are not vacuous run at 32 bits only (the formal-rigour record is in `results/143c/formal_rigour/`).
- No DMA agent run exists yet, so nothing here shows that the agent chooses or wires the engine correctly.

## Course impact

None: the course has no DMA lesson yet. A lesson on descriptors, the 4 KB rule and the cache contract is a follow-up for the planner (`FPGA_Design_Course/lessons`, Part 17 or a new part).
