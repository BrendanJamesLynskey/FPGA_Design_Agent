# Brief 64A results: HW/SW interface

Simulation and out-of-context Vivado 2026.1 builds only; nothing here has run on a board. How each was made:
[docs/hwsw.md](../../docs/hwsw.md).

| File | What | Made by |
|---|---|---|
| `cfu_crc32.json` | cycles of zlib's CRC-32 on the BRV32P RV32 core at 16, 64, 256 and 1024 bytes: table-driven C, bitwise C, carry-less multiply (Zbkc), and the custom instruction `crc32.w` from `ip_lib/crc32_step` (both variants); the check that the software kernels' cycles are identical on all three cores | `python3 hwsw/cfu_core/run_bench.py` (Icarus Verilog 12, riscv64-unknown-elf-gcc 13.2) |
| `core_ooc.json` | the SoC with the pinned core and with each variant: LUTs, flip-flops, DSP, the unit's own LUTs and flip-flops, WNS at 10 ns and the Fmax estimate | `python3 hwsw/cfu_core/core_ooc.py` (Vivado 2026.1, xc7a100tcsg324-1, out of context, one run each) |
| `partition_crc32_zynq.{json,txt}` | the cost model on a Zynq-7000 CRC example whose inputs are all assumptions (verdict: measure) | `python3 -m hwsw.partition hwsw/examples/partition_crc32_zynq.yaml --json ...` |
| `partition_crc32_rv32.{json,txt}` | the cost model on the RV32 core, software against the custom instruction, from the measured cycles and Fmax above | `python3 -m hwsw.partition hwsw/examples/partition_crc32_rv32.yaml --json ...` |
| `../b64a/faults.json` | the five seeded faults of `ip_lib/crc32_step`, each caught | `python3 hil/ip_faults.py --blocks crc32_step --json results/b64a/faults.json` |

Cycles (simulation):

| Core | Kernel | 16 B | 64 B | 256 B | 1024 B | cycles per byte at 1024 B |
|---|---|---|---|---|---|---|
| pinned core | table-driven C (1 KB table) | 208 | 736 | 2848 | 11296 | 11.03 |
| pinned core | bitwise C (no table) | 1040 | 4077 | 16160 | 64544 | 63.03 |
| pinned core | carry-less multiply (Zbkc, Zbkb) | 81 | 201 | 681 | 2615 | 2.55 |
| with crc32_step `word` (latency 1) | custom instruction crc32.w | 62 | 133 | 422 | 1574 | 1.54 |
| with crc32_step `byte` (latency 4) | custom instruction crc32.w | 74 | 181 | 614 | 2342 | 2.29 |

Speed-up of the custom instruction:

| Custom instruction | against | 16 B | 64 B | 256 B | 1024 B |
|---|---|---|---|---|---|
| `word` | table-driven C (1 KB table) | 3.35x | 5.53x | 6.75x | 7.18x |
| `word` | carry-less multiply (Zbkc, Zbkb) | 1.31x | 1.51x | 1.61x | 1.66x |
| `byte` | table-driven C (1 KB table) | 2.81x | 4.07x | 4.64x | 4.82x |
| `byte` | carry-less multiply (Zbkc, Zbkb) | 1.09x | 1.11x | 1.11x | 1.12x |

Cost in the core (Vivado 2026.1, out of context, one run each):

| Core | SoC LUTs | SoC FFs | core LUTs | the unit (LUTs / FFs) | DSP | WNS at 10 ns (ns) | Fmax estimate (MHz) |
|---|---|---|---|---|---|---|---|
| pinned core | 11832 | 7976 | 8625 | - | 16 | -5.914 | 62.8 |
| with crc32_step `word` | 12265 | 8031 | 9057 | 297 / 68 | 16 | -5.471 | 64.6 |
| with crc32_step `byte` | 11955 | 8099 | 8771 | 165 / 127 | 16 | -5.294 | 65.4 |

The generated register blocks' checks (simulation, mutants, formal) are tests, not records: `hwsw/tests/` and the CI job
`hwsw`.
