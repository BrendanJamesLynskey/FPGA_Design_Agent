# HW/SW interface: results

In plain words:
- A CRC-32 unit from the IP library, added to an RV32 5-stage core as one new instruction, runs 7.2 times faster than
  table-driven C (1.54 against 11.0 cycles per byte at 1 KB) and 1.65 times faster than carry-less multiply. It adds
  371 LUTs to the core (4.3 %) with no measured clock-rate loss (one build each).
- Completing the instruction in MEM, as the core's multiplier does, instead of stalling EX saves one clock per
  instruction: 1.29 cycles per byte at 1 KB (8.6 times the table-driven C) against 1.54.
- The pinned core loses an EX-stalled instruction that the branch predictor wrongly predicts taken; a directed test
  shows it, and a one-line patch in our pinned copy fixes it.
- On a Zynq-7000, with every input an assumption, the cost model cannot say whether a DMA-fed CRC block beats the Arm
  core; it names the Arm's cycles per byte as the first thing to measure.
- Answering OKAY instead of SLVERR to unmapped addresses inside a register block costs nothing measurable: one LUT and
  two flip-flops fewer in the example block (one build each).
- The split response (a read of an unmapped address answers SLVERR, a write OKAY) costs 3 LUTs and 1 flip-flop over
  OKAY in the example block; the error-capture registers that record each unmapped access cost 65 LUTs and 20
  flip-flops more (one build each). That is not a few LUTs: about a third more than the 183-LUT block, so the capture
  can be left out with `error_capture: false`.

Simulation and out-of-context Vivado 2026.1 builds only; nothing here has run on a board. How each was made:
[docs/hwsw.md](../../docs/hwsw.md).

## Records

| File | What | Made by |
|---|---|---|
| `cfu_crc32.json` | the wrapper monitor's count of kills by the unit's state (the trap and the timer interrupts; EX style), cycles of zlib's CRC-32 on the BRV32P RV32 core at 16, 64, 256 and 1024 bytes: table-driven C, bitwise C, carry-less multiply (Zbkc), and the custom instruction `crc32.w` from `ip_lib/crc32_step` (both variants, both integration styles: stall in EX, complete in MEM); the check that the software kernels' cycles are identical on all five cores; and the stale-prediction program's result on four cores (`stale_btb`) | `python3 hwsw/cfu_core/run_bench.py` (Icarus Verilog 12, riscv64-unknown-elf-gcc 13.2) |
| `core_ooc.json` | the SoC with the pinned core and with each variant (and `word` with the unit's hierarchy kept, an experiment): LUTs, flip-flops, DSP, the wrapper's and the library unit's LUTs and flip-flops, WNS at 10 ns and the Fmax estimate | `python3 hwsw/cfu_core/core_ooc.py --configs baseline,cfu_word,cfu_byte,cfu_word_keep` (Vivado 2026.1, xc7a100tcsg324-1, out of context, clock read before synthesis, one run each) |
| `core_ooc/<config>/` | the raw Vivado reports each `core_ooc.json` entry is read from: `utilization_hier.rpt`, `timing_summary.rpt`, `critical_path.rpt`, `summary.txt`, and the clock constraint `clock.xdc` | the same run, made with the committed `hwsw/cfu_core/core_ooc.tcl` |
| `core_ooc_styles.json`, `core_ooc_styles/<config>/` | the four patched cores of brief 64A2 (both variants, both styles, all with the mispredict hold patch): the same fields as `core_ooc.json` | `python3 hwsw/cfu_core/core_ooc.py --configs cfu_word,cfu_byte,cfu_word_mem,cfu_byte_mem --out results/64a_hwsw/core_ooc_styles.json --raw results/64a_hwsw/core_ooc_styles` (Vivado 2026.1, one run each) |
| `regmap_ooc.json`, `regmap_ooc/<setting>/` | the example register map `demo_accel` built alone with `unmapped: okay` and with `unmapped: slverr`: LUTs, flip-flops, WNS at 10 ns, and the raw reports | `python3 hwsw/regmap_ooc.py` (Vivado 2026.1, xc7a100tcsg324-1, out of context, one run each) |
| `regmap_ooc_split.json`, `regmap_ooc_split/<setting>/` | brief 64A3: the same example map built alone with `okay`, `slverr` and `split` (each without the error-capture registers) and with `split` plus the capture registers (the new default): LUTs, flip-flops, WNS at 10 ns, the differences, and the raw reports. `okay` and `slverr` reproduce the 64A2 numbers (180/241 and 181/243) | `python3 hwsw/regmap_ooc.py --series 64a3` (Vivado 2026.1, xc7a100tcsg324-1, out of context, one run each) |
| `partition_crc32_zynq.{json,txt}` | the cost model on a Zynq-7000 CRC example whose inputs are all assumptions (verdict: measure) | `python3 -m hwsw.partition hwsw/examples/partition_crc32_zynq.yaml --json ...` |
| `partition_crc32_rv32.{json,txt}` | the cost model on the RV32 core, software against the custom instruction, from the measured cycles and Fmax above | `python3 -m hwsw.partition hwsw/examples/partition_crc32_rv32.yaml --json ...` |
| `../b64a/faults.json` | the five seeded faults of `ip_lib/crc32_step`, each caught | `python3 hil/ip_faults.py --blocks crc32_step --json results/b64a/faults.json` |

Cycles (simulation):

| Core | Kernel | 16 B | 64 B | 256 B | 1024 B | cycles per byte at 1024 B |
|---|---|---|---|---|---|---|
| pinned core | table-driven C (1 KB table) | 208 | 736 | 2848 | 11296 | 11.03 |
| pinned core | bitwise C (no table) | 1042 | 4066 | 16175 | 64546 | 63.03 |
| pinned core | carry-less multiply (Zbkc, Zbkb) | 81 | 201 | 681 | 2602 | 2.54 |
| with crc32_step `word` (latency 1), stall in EX | custom instruction crc32.w | 62 | 133 | 422 | 1574 | 1.54 |
| with crc32_step `byte` (latency 4), stall in EX | custom instruction crc32.w | 74 | 181 | 614 | 2342 | 2.29 |
| with crc32_step `word` (latency 1), complete in MEM | custom instruction crc32.w | 58 | 117 | 358 | 1318 | 1.29 |
| with crc32_step `byte` (latency 4), complete in MEM | custom instruction crc32.w | 70 | 165 | 550 | 2086 | 2.04 |

Speed-up of the custom instruction:

| Custom instruction | against | 16 B | 64 B | 256 B | 1024 B |
|---|---|---|---|---|---|
| `word`, stall in EX | table-driven C (1 KB table) | 3.35x | 5.53x | 6.75x | 7.18x |
| `word`, stall in EX | carry-less multiply (Zbkc, Zbkb) | 1.31x | 1.51x | 1.61x | 1.65x |
| `byte`, stall in EX | table-driven C (1 KB table) | 2.81x | 4.07x | 4.64x | 4.82x |
| `byte`, stall in EX | carry-less multiply (Zbkc, Zbkb) | 1.09x | 1.11x | 1.11x | 1.11x |
| `word`, complete in MEM | table-driven C (1 KB table) | 3.59x | 6.29x | 7.96x | 8.57x |
| `word`, complete in MEM | carry-less multiply (Zbkc, Zbkb) | 1.40x | 1.72x | 1.90x | 1.97x |
| `byte`, complete in MEM | table-driven C (1 KB table) | 2.97x | 4.46x | 5.18x | 5.42x |
| `byte`, complete in MEM | carry-less multiply (Zbkc, Zbkb) | 1.16x | 1.22x | 1.24x | 1.25x |

The stale-prediction program (`hwsw/cfu_core/bench/stale_btb.c`, `word` variant): RESULT FAIL on the EX style with the
pinned core's mispredict logic (the instruction is lost), RESULT PASS on the EX style with the hold patch and on the MEM
style with and without it.

Cost in the core (Vivado 2026.1, out of context, one run each):

| Core | SoC LUTs | SoC FFs | core LUTs | wrapper (LUTs / FFs) | library unit inside it (LUTs / FFs) | DSP | WNS at 10 ns (ns) | Fmax estimate (MHz) |
|---|---|---|---|---|---|---|---|---|
| pinned core | 11854 | 7917 | 8663 | - | - | 16 | -6.123 | 62.0 |
| with crc32_step `word` | 12254 | 8042 | 9034 | 285 / 133 | 283 / 33 | 16 | -5.233 | 65.6 |
| with crc32_step `byte` | 12004 | 8160 | 8811 | 182 / 192 | 179 / 92 | 16 | -6.210 | 61.7 |
| `word`, the unit's hierarchy kept (an experiment) | 12273 | 8043 | 9050 | 295 / 133 | 97 / 33 | 16 | -5.413 | 64.9 |

With the unit's hierarchy kept it takes 97 LUTs (95 out of context) and the core grows by about the same (387 against
371): the 283 includes logic from outside the unit, most likely the operand multiplexers, merged into it (one run each). Read the cost as the core's growth.

Both integration styles, rebuilt with the mispredict hold patch for brief 64A2 (`core_ooc_styles.json`, raw reports in `core_ooc_styles/`; the pinned core is the 64A baseline above, one run each):

| Core | SoC LUTs | SoC FFs | core LUTs | wrapper (LUTs / FFs) | library unit inside it (LUTs / FFs) | DSP | WNS at 10 ns (ns) | Fmax estimate (MHz) |
|---|---|---|---|---|---|---|---|---|
| pinned core | 11854 | 7917 | 8663 | - | - | 16 | -6.123 | 62.0 |
| with crc32_step `word`, stall in EX | 12290 | 8107 | 9095 | 464 / 133 | 461 / 33 | 16 | -5.145 | 66.0 |
| with crc32_step `byte`, stall in EX | 11962 | 8141 | 8768 | 181 / 192 | 178 / 92 | 16 | -5.987 | 62.6 |
| with crc32_step `word`, complete in MEM | 12042 | 8031 | 8856 | 905 / 66 | 905 / 33 | 16 | -5.910 | 62.9 |
| with crc32_step `byte`, complete in MEM | 11963 | 8139 | 8757 | 366 / 125 | 363 / 92 | 16 | -6.448 | 60.8 |

| Variant | style | core LUTs (growth) | core FFs (growth) | Fmax estimate (MHz) | cycles per byte at 1 KB |
|---|---|---|---|---|---|
| `word` | stall in EX | 9095 (+432) | 6967 (+190) | 66.0 | 1.54 |
| `byte` | stall in EX | 8768 (+105) | 7001 (+224) | 62.6 | 2.29 |
| `word` | complete in MEM | 8856 (+193) | 6891 (+114) | 62.9 | 1.29 |
| `byte` | complete in MEM | 8757 (+94) | 6999 (+222) | 60.8 | 2.04 |

The same EX-style `word` core grew by 371 LUTs in the 64A run and by 432 here: the two builds differ by the one-gate hold patch and by the run, so the spread is not separated. Completing in MEM is one clock per instruction faster (simulation) and, in these builds, not larger.

The generated register blocks' checks (simulation, mutants, formal) are tests, not records: `hwsw/tests/` and the CI job
`hwsw`.

## Reproduce

The command for each record is in the "Made by" column above. In short: `python3 hwsw/cfu_core/run_bench.py` (simulation: Icarus Verilog
and the RISC-V cross compiler, no Vivado); `python3 hwsw/cfu_core/core_ooc.py` and `python3 hwsw/regmap_ooc.py [--series 64a2|64a3]` (Vivado 2026.1, heavy
slot, one run per configuration); `python3 -m hwsw.partition <example yaml> --json ...` (cost model, no tools). No board is involved.

## Known gaps and limits

- Simulation and out-of-context builds only; nothing here has run on a board.
- One Vivado run per configuration: the spread between the two EX-style builds of the same variant (371 and 432 LUTs) is not separated from run-to-run placement.
- Every core variant misses 100 MHz out of context (WNS negative at 10 ns); the Fmax figures are estimates, not timing closure.
- The Zynq cost model has only assumed inputs and returns "measure"; the Arm core's cycles per byte were not measured.
- The stale-prediction defect is shown by a directed test; the fix is a one-line patch in our pinned copy of the core, not an upstream change.
- The register-block checks (simulation, mutants, formal) are tests, not records, so they are not repeated here.
- What an Arm CPU does with a SLVERR on a load and on a posted write is expected from Arm documentation, not measured here (brief 64B item 5); the datasheets say "expected". The hand-written block-design register banks (`flow/blockdesign/rtl`) still answer SLVERR to unmapped writes and have no error capture.
