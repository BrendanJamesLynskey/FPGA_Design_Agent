# HW/SW interface: results

In plain words:
- A CRC-32 unit from the IP library, added to an RV32 5-stage core as one new instruction, runs 7.2 times faster than
  table-driven C (1.54 against 11.0 cycles per byte at 1 KB) and 1.65 times faster than carry-less multiply. It adds
  371 LUTs to the core (4.3 %) with no measured clock-rate loss (one build each).
- On a Zynq-7000, with every input an assumption, the cost model cannot say whether a DMA-fed CRC block beats the Arm
  core; it names the Arm's cycles per byte as the first thing to measure.

Simulation and out-of-context Vivado 2026.1 builds only; nothing here has run on a board. How each was made:
[docs/hwsw.md](../../docs/hwsw.md).

| File | What | Made by |
|---|---|---|
| `cfu_crc32.json` | the wrapper monitor's count of kills by the unit's state (the trap and the timer interrupts), and cycles of zlib's CRC-32 on the BRV32P RV32 core at 16, 64, 256 and 1024 bytes: table-driven C, bitwise C, carry-less multiply (Zbkc), and the custom instruction `crc32.w` from `ip_lib/crc32_step` (both variants); the check that the software kernels' cycles are identical on all three cores | `python3 hwsw/cfu_core/run_bench.py` (Icarus Verilog 12, riscv64-unknown-elf-gcc 13.2) |
| `core_ooc.json` | the SoC with the pinned core and with each variant (and `word` with the unit's hierarchy kept, an experiment): LUTs, flip-flops, DSP, the wrapper's and the library unit's LUTs and flip-flops, WNS at 10 ns and the Fmax estimate | `python3 hwsw/cfu_core/core_ooc.py --configs baseline,cfu_word,cfu_byte,cfu_word_keep` (Vivado 2026.1, xc7a100tcsg324-1, out of context, clock read before synthesis, one run each) |
| `core_ooc/<config>/` | the raw Vivado reports each `core_ooc.json` entry is read from: `utilization_hier.rpt`, `timing_summary.rpt`, `critical_path.rpt`, `summary.txt`, and the clock constraint `clock.xdc` | the same run, made with the committed `hwsw/cfu_core/core_ooc.tcl` |
| `partition_crc32_zynq.{json,txt}` | the cost model on a Zynq-7000 CRC example whose inputs are all assumptions (verdict: measure) | `python3 -m hwsw.partition hwsw/examples/partition_crc32_zynq.yaml --json ...` |
| `partition_crc32_rv32.{json,txt}` | the cost model on the RV32 core, software against the custom instruction, from the measured cycles and Fmax above | `python3 -m hwsw.partition hwsw/examples/partition_crc32_rv32.yaml --json ...` |
| `../b64a/faults.json` | the five seeded faults of `ip_lib/crc32_step`, each caught | `python3 hil/ip_faults.py --blocks crc32_step --json results/b64a/faults.json` |

Cycles (simulation):

| Core | Kernel | 16 B | 64 B | 256 B | 1024 B | cycles per byte at 1024 B |
|---|---|---|---|---|---|---|
| pinned core | table-driven C (1 KB table) | 208 | 736 | 2848 | 11296 | 11.03 |
| pinned core | bitwise C (no table) | 1042 | 4066 | 16175 | 64546 | 63.03 |
| pinned core | carry-less multiply (Zbkc, Zbkb) | 81 | 201 | 681 | 2602 | 2.54 |
| with crc32_step `word` (latency 1) | custom instruction crc32.w | 62 | 133 | 422 | 1574 | 1.54 |
| with crc32_step `byte` (latency 4) | custom instruction crc32.w | 74 | 181 | 614 | 2342 | 2.29 |

Speed-up of the custom instruction:

| Custom instruction | against | 16 B | 64 B | 256 B | 1024 B |
|---|---|---|---|---|---|
| `word` | table-driven C (1 KB table) | 3.35x | 5.53x | 6.75x | 7.18x |
| `word` | carry-less multiply (Zbkc, Zbkb) | 1.31x | 1.51x | 1.61x | 1.65x |
| `byte` | table-driven C (1 KB table) | 2.81x | 4.07x | 4.64x | 4.82x |
| `byte` | carry-less multiply (Zbkc, Zbkb) | 1.09x | 1.11x | 1.11x | 1.11x |

Cost in the core (Vivado 2026.1, out of context, one run each):

| Core | SoC LUTs | SoC FFs | core LUTs | wrapper (LUTs / FFs) | library unit inside it (LUTs / FFs) | DSP | WNS at 10 ns (ns) | Fmax estimate (MHz) |
|---|---|---|---|---|---|---|---|---|
| pinned core | 11854 | 7917 | 8663 | - | - | 16 | -6.123 | 62.0 |
| with crc32_step `word` | 12254 | 8042 | 9034 | 285 / 133 | 283 / 33 | 16 | -5.233 | 65.6 |
| with crc32_step `byte` | 12004 | 8160 | 8811 | 182 / 192 | 179 / 92 | 16 | -6.210 | 61.7 |
| `word`, the unit's hierarchy kept (an experiment) | 12273 | 8043 | 9050 | 295 / 133 | 97 / 33 | 16 | -5.413 | 64.9 |

With the unit's hierarchy kept it takes 97 LUTs (95 out of context) and the core grows by about the same (387 against
371): the 283 includes logic from outside the unit, most likely the operand multiplexers, merged into it (one run each). Read the cost as the core's growth.

The generated register blocks' checks (simulation, mutants, formal) are tests, not records: `hwsw/tests/` and the CI job
`hwsw`.
