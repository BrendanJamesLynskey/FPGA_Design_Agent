# HW/SW interface and partitioning

Three tools for the boundary between a processor and the fabric (brief 64A and 64A+). Everything here was checked in
simulation; nothing has run on a board yet (that is brief 64B, on the ZedBoard).

1. **Register-map single source** (`hwsw/regmap.py`): one YAML file generates the AXI4-Lite register block, the C header,
   the Python host driver and the documentation, and a check proves the four agree.
2. **Partitioning cost model** (`hwsw/partition.py`): time and energy per call of a kernel as software, as a custom
   instruction and as an accelerator behind DMA, over a range of sizes, with the break-even sizes, Amdahl's limit and a
   decision with its reasons.
3. **IP library entry as a custom instruction** (`hwsw/cfu.py`): an `ip_lib` entry that declares a function-unit
   contract becomes a unit in a CPU's pipeline. Measured on a pinned copy of the owner's RV32 core.

**Try it** (Python 3, PyYAML; the simulations need Icarus Verilog 12 and cocotb 2.0.1, the core bench
`riscv64-unknown-elf-gcc`, the formal check SymbiYosys):

```
python3 -m hwsw.regmap check hwsw/examples/demo_accel.yaml          # the four outputs current and in agreement
python3 -m hwsw.partition hwsw/examples/partition_crc32_zynq.yaml   # CRC-32 on a Zynq-7000: break-even, Amdahl, verdict
python3 -m pytest -q hwsw/tests                                      # everything below (about 15 minutes)
python3 hwsw/cfu_core/run_bench.py                                   # crc32_step in the RV32 core against software
```

## Words used here

| Term | Meaning |
|---|---|
| Register block | the logic that holds a block's control and status registers and answers the CPU's reads and writes |
| AXI4-Lite | Arm's simple memory-mapped bus: one 32-bit read or write at a time, each with a response |
| W1C, W1S, W1P | write 1 to clear, write 1 to set, write 1 to pulse: access types for events, doorbells and commands |
| Doorbell | a register write that tells the hardware new work is ready |
| DMA | direct memory access: an engine that moves data between memory and the fabric without the CPU |
| Coherent port | a fabric-to-memory port that sees the CPU's caches, so software needs no cache maintenance |
| Custom instruction (CI) | a new CPU instruction executed by a unit added to the pipeline |
| Break-even size | the problem size above which the accelerator path is faster than software |
| Amdahl's limit | 1 / (1 - p): the most a whole program can gain when a fraction p of its time is sped up |
| Stall | a clock in which the pipeline waits and no instruction completes |

## 1. Register-map single source

### The format (`regmap: 1`)

```yaml
regmap: 1
name: demo_accel            # lower case; the module is demo_accel_regs, the C prefix DEMO_ACCEL_
version: 0.1.0
addr_width: 12              # a 4 KB window (only address bits [11:2] are decoded)
unmapped: slverr            # or okay: the answer to an address no register decodes
interrupt: {status: IRQ_STATUS, enable: IRQ_ENABLE}
registers:
- name: CTRL
  offset: 0x004
  fields:
  - {name: ENABLE, lsb: 0, width: 1, access: RW, reset: 0}
  - {name: OVERFLOW, lsb: 8, width: 1, access: W1C}
- name: CMD
  offset: 0x008
  fields:
  - {name: START, lsb: 0, width: 1, access: W1P}
```

| Access | Software | Hardware port |
|---|---|---|
| `RW` | reads and writes the value | `<reg>_<field>_o` |
| `RO` | reads; writes are ignored | `<reg>_<field>_i`, or a constant with `const:` |
| `W1C` | writing 1 clears a bit; a hardware set in the same clock wins | `<reg>_<field>_set_i` (pulse), `_o` (value) |
| `W1S` | writing 1 sets a bit; it wins over a hardware clear in the same clock | `<reg>_<field>_clr_i` (pulse), `_o` (value) |
| `W1P` | writing 1 gives a one-clock pulse; reads 0 | `<reg>_<field>_pulse_o` |

There is no clear-on-read type, on purpose: a read with a side effect breaks debuggers, repeated reads and
read-modify-write (the knowledge-bank skill `register-maps-for-software` gives the rules). The interrupt output `irq_o`
is high while any status bit is set together with its enable bit, one clock after the cause.

The loader refuses, with every reason listed: overlapping registers or fields, offsets that are not word-aligned or
fall outside the window, reset or constant values wider than their field, unknown access types or keys, a reset on a
hardware input, a W1P reset other than 0, duplicate names, generated port names that collide, names that clash with
the generated register-level names, two registers whose C names would meet, an interrupt status register with non-W1C fields or bits without an enable.

### What is generated

| Output | What it holds |
|---|---|
| `<name>_regs.sv` | the AXI4-Lite slave (AW and W captured independently in either order, byte strobes honoured bit by bit, one outstanding read and write, synchronous active-low reset), the field storage and the read multiplexer, `ADDR_` and `RESET_` constants |
| `<name>_regs.h` | per register `_OFFSET`, `_RESET` and a mask per access type (`_RW_MASK` is the read-modify-write mask); per field `_SHIFT`, `_WIDTH`, `_MASK`, `_RESET`, `_ACCESS`; `GET`/`PUT` macros and read and write functions whose bus access can be replaced before the header is included |
| `<name>_regs.py` | the table, a blocking driver and the same driver for a bus whose calls are coroutines (a simulation bus), and a memory-mapped bus for a UIO device or `/dev/mem`; `set` keeps the other RW fields and writes W1C, W1S and W1P bits as 0, so it never clears an event by accident |
| `<name>_regs.md` | the map, each register's fields, the access types and the hardware ports |

All four carry the SHA-256 of the map's content, so a stale output is easy to spot.

### How agreement is checked

`python3 -m hwsw.regmap check <map.yaml>` does two things:

- **Drift:** every output is regenerated and compared with the file on disk; a hand edit or a changed YAML fails.
- **Agreement:** each output is read back on its own terms and compared with the YAML: the C header by compiling a probe
  program that prints every generated constant; the Python driver by importing it; the markdown by parsing its tables;
  the SystemVerilog by its port list and its address and reset constants.

`hwsw/tests/test_64a_regmap.py` edits each output by hand in 13 ways (a mask, a reset, an access type, an offset, a port
width) and checks that the agreement check names each one, and breaks 22 rules of the format and checks that the
loader refuses each.

### How the generated RTL is verified

`hwsw/tests/test_64a_regmap_rtl.py` simulates two maps under cocotb and Icarus Verilog 12: the example `demo_accel`
(11 registers, every access type, an interrupt) and a map of awkward layouts (fields across byte lanes, a 32-bit field,
multi-bit W1C, W1S and W1P fields, a register at the top of a 64-byte window, unmapped addresses answered OKAY). The
bench reaches the RTL only through the **generated Python driver** over an AXI4-Lite master with random VALID delays, a
random order of AW and W, and random BREADY and RREADY back-pressure. The brief 59A AXI4-Lite protocol checker
(`axi_tx/rtl/axil_checker.sv`) watches the same wires and fails the test on any rule. Tests:

- every register's reset value, and every stored field's output after reset;
- each access type, field by field, through the driver's own calls (`set`, `clear`, `ring`, `pulse`), with the hardware
  ports checked and the W1P pulses counted;
- the same-clock races: a hardware set during a W1C clear, and a hardware clear during a W1S ring, both timed to the
  commit clock;
- 8 random byte-strobe writes per register against a model built from the YAML alone;
- unmapped addresses (all of them in the small map, 64 sampled in the 4 KB one): response, read value, no side effect;
- the interrupt line over 30 random set, clear, enable and disable steps;
- the driver's read-modify-write keeps a pending W1C event; a naive write-back of the read value clears it;
- a soak of 400 random operations (reads, whole-word and strobed writes, hardware events, input changes) at three
  back-pressure levels, every read compared with the model;
- for `demo_accel`, a **C driver** (`hwsw/examples/demo_accel_driver.c`, written against the generated header) runs
  against the RTL: its bus accesses go over a pipe to the bench (`hwsw/tests/c_cosim_harness.c`), a small model of the
  accelerator answers START with BUSY and then DONE, and the driver completes three polled and three interrupt-driven
  jobs. The same driver source compiles for the Cortex-A9 with `arm-none-eabi-gcc -mcpu=cortex-a9`.

Seven seeded faults in the generated RTL (a clear that beats a set, byte strobes ignored, OKAY for unmapped addresses,
B before W, a lost doorbell, an interrupt that ignores its enable, a pulse that stays high) must each fail the bench;
all seven do. The B-before-W fault is caught by the protocol checker (rule 5, B_EARLY).

`hwsw/tests/test_64a_regmap_formal_rtl.py` checks the AXI4-Lite handshake formally with SymbiYosys on both maps: every
master-side signal and hardware input free, the master assumed to keep its side of the protocol, and the slave's rules
asserted (B and R held until READY, no B before both AW and W, no R before AR, no EXOKAY, no VALID in reset). Bounded to
20 clocks; a cover task shows that a write and a read can complete (the proof is not vacuous); two seeded handshake
faults are found. An unbounded proof (k-induction) does not converge without invariants that tie the block's state to
the checker's counters; that is a follow-up. With yosys 0.33 and z3 4.8.12, the larger map needs `smtbmc --unroll`: without it
the solver did not finish the first step in 25 seconds.

## 2. Partitioning cost model

See the knowledge-bank skills `hw-sw-partitioning-cost-model` and `custom-instruction-or-accelerator` for the rules;
this is the executable form. Inputs are a YAML file: the problem sizes, the application's kernel fraction p, and per
option its inputs, each a number or a `[low, high]` range **with a source** (a results file, a document, or
"assumption"). The model evaluates every corner of the ranges and reports each output as low .. high.

Time per call for N items:

- software: `(C_call + c_item * N) / f_cpu`
- custom instruction: `(C_call + c_item * N) / f_core`
- accelerator: `setup + cache maintenance + body + done`, where the body is in + compute + out for a store-and-forward
  job, or the slowest of the three plus the pipeline fill for a streaming one; done is the interrupt latency or one
  status read.

It reports per size the times, energies and speed-ups; where one option starts to beat another (and in how many input
corners it never does); Amdahl's limit and the whole-application speed-up at the typical size; which input moves the
answer most (one at each end, the others mid-range: the order in which to measure); and the decision.

`decide()` applies the decision rules: a custom instruction needs at most two source registers and one result, little
or no state, no memory access of its own, a latency the pipeline can stall for (4 clocks by default) and an Fmax that
does not slow the core; an accelerator needs calls above its break-even size; either needs a whole-application gain of
at least 1.1 at every corner, and when the interval straddles that the verdict is **measure**, not a choice. Missing
traits are reported as unknown, never assumed.

## 3. An IP library entry as a custom instruction

### The contract

An `ip_lib` entry declares, beside its parameters and variants, how a CPU would drive it:

```yaml
function_unit:
  operation: crc32.w
  summary: rd = CRC-32 update of rs1 by the 4 bytes of rs2, least significant byte first (no inversion)
  operands: {rs1: crc_in, rs2: data_in}
  result: {rd: crc_out}
  issue: in_valid          # one-clock pulse with the operands
  done: out_valid          # one-clock pulse with the result, the variant's latency later
  state: none
  model: ip_lib/crc32_step/model.py:crc32_word
```

`python3 -m hwsw.cfu --check` checks every such contract against the rules of the decision skill (at most two source
registers and one result, no state, ports present in the RTL, a latency of at least 1 and, unless `--allow-long` is
given, at most 4 clocks). `python3 -m hwsw.cfu crc32_step --variant word --out DIR` writes:

- `cfu_crc32_step.sv`: the unit behind the port a simple in-order pipeline uses for a multi-cycle execute unit (the
  BRV32P core's divider handshake: `start`, `hold`, `kill` in; `busy`, `valid`, `result` out). The instruction waits in
  EX while `busy` is high; a finished result is held while the pipeline is stalled; an operation killed in EX (by an
  older instruction's trap) is left to finish inside the unit and its result dropped, and the retried instruction waits
  for it;
- `cfu_ops.vh`: the module name and the encodings the core's decoder accepts (anything else stays illegal);
- `cfu_crc32_step.h`: `crc32_w(rs1, rs2)` for C, written with the GNU assembler's `.insn` directive (R-type, custom-2
  opcode `0x5b`), so no compiler change is needed.

### The first entry: `crc32_step`

[ip_lib/crc32_step](../ip_lib/crc32_step/README.md) is one CRC-32 update (IEEE 802.3, reflected) by a 32-bit word: two
operands, one result, no state; the running CRC lives in a register between calls. Two variants: `word` (the whole
update in one clock, latency 1) and `byte` (one byte per clock, latency 4). Both are bit-exact against `model.py` and
against zlib over whole buffers, with latency and II measured; five seeded faults are each caught. Measured out of
context with Vivado 2026.1 on the xc7a100t: `word` 95 LUTs and 33 flip-flops, `byte` 96 LUTs and 92 flip-flops, so at 32
bits the byte-serial form saves nothing and costs three clocks more per word; it stays as the multi-cycle test case.

### Measured in the owner's RV32 core (simulation)

The core is BRV32P (the owner's `RISCV_RV32IMC_5stage`, a 5-stage RV32IMC with caches, branch prediction and the
Xbrvdsp, Zk, GF and mod-q extensions). That repository belongs to another project and is read-only here, so a copy pinned
at commit `8d53700` lives in `hwsw/cfu_core/brv32p/` ([PINNED.md](../hwsw/cfu_core/PINNED.md), MIT), and the changes that
wire a unit in are a patch applied to a copy in `build/` ([brv32p_cfu.patch](../hwsw/cfu_core/brv32p_cfu.patch): a
custom-2 decode, the unit instance in EX, its result on the existing extension-unit path, and its `busy` into the
divider's stall input). `python3 hwsw/cfu_core/run_bench.py` compiles one program
([crc_bench.c](../hwsw/cfu_core/bench/crc_bench.c), GCC 13.2, `-O2`) that computes zlib's CRC-32 four ways at four
sizes and checks every result against zlib, and runs it on the pinned core and on the core with each variant, in the
core's own test bench under Icarus Verilog 12. Cycles are counted between two marker instructions, with the caches warmed
by a first call. The baseline core runs the same binary with the custom-instruction calls switched off by one data word,
so the software kernels are at the same addresses everywhere: their cycle counts are identical on all three cores (the
patch changes nothing else). The program also makes a misaligned load trap with the custom instruction right behind it
in EX, and checks that the retried instruction returns the right value.

| Core | Kernel | 16 B | 64 B | 256 B | 1024 B | cycles per byte at 1024 B |
|---|---|---|---|---|---|---|
| pinned core | table-driven C (1 KB table) | 208 | 736 | 2848 | 11296 | 11.03 |
| pinned core | bitwise C (no table) | 1040 | 4077 | 16160 | 64544 | 63.03 |
| pinned core | carry-less multiply (Zbkc, Zbkb) | 81 | 201 | 681 | 2615 | 2.55 |
| with crc32_step `word` (latency 1) | custom instruction crc32.w | 62 | 133 | 422 | 1574 | 1.54 |
| with crc32_step `byte` (latency 4) | custom instruction crc32.w | 74 | 181 | 614 | 2342 | 2.29 |

Speed-up of the custom instruction (cycles of the software kernel / cycles with the instruction, same core):

| Custom instruction | against | 16 B | 64 B | 256 B | 1024 B |
|---|---|---|---|---|---|
| `word` | table-driven C (1 KB table) | 3.35x | 5.53x | 6.75x | 7.18x |
| `word` | carry-less multiply (Zbkc, Zbkb) | 1.31x | 1.51x | 1.61x | 1.66x |
| `byte` | table-driven C (1 KB table) | 2.81x | 4.07x | 4.64x | 4.82x |
| `byte` | carry-less multiply (Zbkc, Zbkb) | 1.09x | 1.11x | 1.11x | 1.12x |

The cycle counts are exact straight lines in the size: the `word` instruction costs 38 + 1.5 cycles per byte, that is 6
cycles per word for 5 instructions (load, two adds, the instruction, the branch) plus one stall clock; `byte` costs 38 +
2.25 cycles per byte, three stall clocks more per word, exactly its extra latency. The table-driven C costs 32 + 11
cycles per byte. So the low-latency variant is the one to wrap, as the decision skill says.

OOC_SECTION

### What this does not show

- No board run: the core with the unit has not been built for or run on the Nexys A7 or a Zynq.
- One kernel, one compiler, one core. The cycle counts are for this core's caches and branch predictor at these sizes.
- The stall-based port costs one clock per instruction for a 1-clock unit; completing in MEM, as the core's multiplier
  does, would hide it for independent instructions. Not built.
- The decoder accepts one encoding per generated unit; several units on one opcode need a funct-based selector.
