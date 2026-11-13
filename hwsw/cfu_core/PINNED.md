# Pinned copy of the BRV32P core (read-only source)

Source: https://github.com/BrendanJamesLynskey/RISCV_RV32IMC_5stage, commit 8d5370039e93b0e07943a20146170eb6bb189018
(2026-11-09, "Merge pull request #36 from BrendanJamesLynskey/cache-sweeps"), copied with `git archive` on 2026-11-13.

Licence: MIT, as the source repository's README states ("## Licence: MIT"); copyright the repository's author. The
repository has no separate LICENSE file; this note records the licence statement it makes.

What is copied (`brv32p/`, unchanged): `rtl/` (the core, caches, bus, peripherals, SoC), `tests/isa/tb_isa.v` and
`tests/isa/elf2hex.py` (the test bench and hex converter), and from `tests/bench/`: `crt.S`, `link.ld`, `bench.h`,
`crc32.c` (table-driven CRC-32) and `crc32_zk.c` (CRC-32 by carry-less multiply, Zbkb/Zbkc).

The source repository belongs to another project and is never written from here. Changes needed to wire a generated
custom-instruction unit into the core live in `brv32p_cfu.patch`, applied to a copy in `build/` by `run_bench.py`:

- `rtl/pkg/brv32p_defs.vh`: the custom-2 opcode constant;
- `rtl/core/decoder.v`: custom-2 R-type decode, legal encodings from the generated `cfu_ops.vh`, the rest illegal;
- `rtl/core/brv32p_core.v`: the unit instance in EX (start, hold = memory stall, kill = EX flush, forwarded operands),
  its result on the WB_DSP path, and its busy ORed into the divider's stall input of the hazard unit.

Any change to the copy must be a new pin (a fresh `git archive` of a named commit), never an edit in place.
