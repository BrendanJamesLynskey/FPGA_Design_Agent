# HW/SW interface and partitioning

**What this is for.** When a task has a processor part and a hardware part, these tools help decide what goes where,
build the interface between the two, and check it.

**Results in plain words.**
- A CRC-32 unit from the IP library, added to an RV32 5-stage core as one new instruction, runs 7.2 times faster than
  the usual table-driven C (1.54 against 11.0 clock cycles per byte at 1 KB), and 1.65 times faster than the same CRC
  done with the carry-less multiply instructions. It adds 371 LUTs to the core (4.3 % of its 8,663) with no measured loss of clock rate (one build each). Simulation and out-of-context builds only.
- On a Zynq-7000, with every input an assumption, the cost model cannot say whether a DMA-fed CRC block beats the Arm
  core. It names the one measurement to take first: the Arm's cycles per byte.
- The register-map generator makes the hardware block, the C header, the Python driver and the document from one file,
  and a check proves the four agree.

Three tools for the boundary between a processor and the fabric (brief 64A and 64A+). Everything here was checked in
simulation; nothing has run on a board yet (that is brief 64B, on the ZedBoard).

1. **Register-map single source** (`hwsw/regmap.py`): one YAML file generates the AXI4-Lite register block, the C header,
   the Python host driver and the documentation, and a check proves the four agree.
2. **Partitioning cost model** (`hwsw/partition.py`): time and energy per call of a kernel as software, as a custom
   instruction and as an accelerator behind DMA, over a range of sizes, with the break-even sizes, Amdahl's limit and a
   decision with its reasons.
3. **IP library entry as a custom instruction** (`hwsw/cfu.py`): an `ip_lib` entry that declares a function-unit
   contract becomes a unit in a CPU's pipeline. Measured on a pinned copy of an RV32 5-stage core.

**Try it** (Python 3, PyYAML; the simulations need Icarus Verilog 12 and cocotb 2.0.1, the core bench
`riscv64-unknown-elf-gcc`, the formal check SymbiYosys):

```
python3 -m hwsw.regmap check hwsw/examples/demo_accel.yaml          # the four outputs current and in agreement
python3 -m hwsw.partition hwsw/examples/partition_crc32_zynq.yaml   # CRC-32 on a Zynq-7000: break-even, Amdahl, verdict
python3 -m hwsw.cfu --check                                          # every function-unit contract against the rules
python3 hwsw/cfu_core/run_bench.py                                   # crc32_step in the RV32 core against software
python3 -m pytest -q hwsw/tests                                      # everything below (5 to 15 minutes, by machine)
```

What success looks like (the last line of each):

| Command | Last line |
|---|---|
| `hwsw.regmap check` | `hwsw/examples/demo_accel.yaml: agree (demo_accel_regs.sv, demo_accel_regs.h, demo_accel_regs.py, demo_accel_regs.md)` |
| `hwsw.partition` (Zynq example) | `Decision: measure`, then its two reasons (the accelerator's break-even is unsure; its gain straddles 1.1) |
| `hwsw.cfu --check` | `1 entries with a function_unit contract, 0 problems` |
| `run_bench.py` | `wrote .../results/64a_hwsw/cfu_crc32.json`, after `RESULT PASS` for the baseline and both variants |
| `pytest` | `N passed` with no failures (the core bench and the formal tests are skipped without their tools) |

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
| EX | the execute stage of the pipeline, where a custom instruction's unit runs |
| CFU | custom function unit: the unit behind a custom instruction (the code uses the short form: `cfu.py`, `cfu_core/`) |
| Zbkc, Zbkb | RISC-V bit-manipulation extensions for cryptography; Zbkc is carry-less multiply |
| UIO | Linux userspace I/O: a device file that lets a program map a block's registers and wait for its interrupt, with no driver of its own |
| HP, HPC, ACP, ACE | Zynq PS ports for the fabric: HP high-performance (not coherent); HPC high-performance coherent (Zynq UltraScale+); ACP accelerator coherency port, into the CPU's caches; ACE two-way coherent |
| II | initiation interval: the clocks between one new input and the next |
| Fmax | the highest clock rate a design meets timing at; here estimated as 1000 / (period - WNS) MHz from one routed run |
| WNS | worst negative slack: how far the slowest path misses (negative) or meets (positive) the target clock period |
| Out of context | a block built on its own, not inside a design; its ports have no surrounding logic, so paths from them are untimed unless constrained |

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
the generated register-level names, two registers whose C names would meet, an interrupt status register with non-W1C fields or bits without an enable,
register names the block uses for its own signals (`HIT`, `COMMIT`, `VALUE`: `wr_hit`, `wr_commit`, `rd_value`), and
text that would break an output: a newline or other control character, `*/`, `/*`, `"""`, a backslash or `|` in a
summary, or a version that is not letters, digits and `. + _ -`. `gen` checks the text again before it writes.

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
  the SystemVerilog by its port list and its address and reset constants, and by compiling it with Icarus Verilog
  (`iverilog -g2012`) when that is installed.

`hwsw/tests/test_64a_regmap.py` edits each output by hand in 13 ways (a mask, a reset, an access type, an offset, a port
width) and checks that the agreement check names each one, and breaks 31 rules of the format and checks that the
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
- a second read address while the first read's response waits for RREADY: ARREADY stays low and R stays steady until
  the response is taken, then the second read returns its own register; and unaligned addresses, which reach the word
  that holds them (address bits [1:0] are not decoded);
- a soak of 400 random operations (reads, whole-word and strobed writes, hardware events, input changes) at three
  back-pressure levels, every read compared with the model;
- for `demo_accel`, a **C driver** (`hwsw/examples/demo_accel_driver.c`, written against the generated header) runs
  against the RTL: its bus accesses go over a pipe to the bench (`hwsw/tests/c_cosim_harness.c`), a small model of the
  accelerator answers START with BUSY and then DONE, and the driver completes three polled and three interrupt-driven
  jobs. The same driver source compiles for the Cortex-A9 with `arm-none-eabi-gcc -mcpu=cortex-a9`.

Eight seeded faults in the generated RTL (a clear that beats a set, byte strobes ignored, OKAY for unmapped addresses,
B before W, a lost doorbell, an interrupt that ignores its enable, a pulse that stays high, ARREADY high while a read
response waits) must each fail the bench; all eight do. The B-before-W fault is caught by the protocol checker (rule 5, B_EARLY).

`hwsw/tests/test_64a_regmap_formal_rtl.py` checks the AXI4-Lite handshake formally with SymbiYosys on both maps: every
master-side signal and hardware input free, the master assumed to keep its side of the protocol, and the slave's rules
asserted (B and R held until READY, no B before both AW and W, no R before AR, no EXOKAY, no VALID in reset). Bounded to
20 clocks; a cover task shows that a write and a read can complete (the proof is not vacuous); three seeded handshake
faults are found (B before W, R dropped early, ARREADY high while R waits). An unbounded proof (k-induction) does not converge without invariants that tie the block's state to
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
  job, or for a streaming one the slowest of the three streams plus the pipeline fill, counted once; done is the
  interrupt latency or one status read.

It reports per size the times, energies and speed-ups; where one option starts to beat another (and in how many input
corners it never does); Amdahl's limit and the whole-application speed-up at the typical size; which input moves the
answer most (one at each end, the others mid-range: the order in which to measure); and the decision.

`decide()` applies the decision rules: a custom instruction needs at most two source registers and one result, little
or no state, no memory access of its own, a latency the pipeline can stall for (4 clocks by default) and an Fmax that
does not slow the core (measured as the core's Fmax with the unit against without it, when that is known); an
accelerator needs calls above its break-even size at every corner, and when some corners never break even it is
reported as unsure, with how many corners, and cannot be chosen; either needs a whole-application gain of at least 1.1
at every corner, and when the interval straddles that the verdict is **measure**, not a choice. An option that passes
its rules but has no speed-up figure also makes the verdict **measure**, never software. Missing traits are reported as
unknown, never assumed. Rates and clock frequencies of zero or below are refused as input errors.

When two options both pass and their worst-case gains are within 5 %, the one with fewer assumed inputs is chosen and
the near tie is stated; a chosen option that rests on assumptions carries a reason saying they must be measured first.

Two worked inputs, with their outputs in [results/64a_hwsw](../results/64a_hwsw/README.md):

- `hwsw/examples/partition_crc32_zynq.yaml`: CRC-32 on a Zynq-7000, the A9 against a fabric CRC behind AXI DMA. Every
  input is an assumption with a wide range. The accelerator is faster from 82 to 451 bytes in 512 of the 1024 input
  corners and never in the other 512 (where the A9 at 2 cycles per byte outruns a 32-bit DMA port). The application
  speed-up at 1500 bytes is 0.44 to 1.81 against a ceiling of 1.43 to 2.5. Verdict: **measure**, the A9's cycles per byte first.
- `hwsw/examples/partition_crc32_rv32.yaml`: the three options on the BRV32P core. Software and the custom instruction use
  the measured cycles and Fmax of section 3; the accelerator (the SoC has no DMA yet) is all assumptions. The custom
  instruction is 3.35 to 7.33 times the table-driven C over the sizes. The application gain at 256 bytes is 1.34 to 2.05
  with the custom instruction and 1.37 to 2.37 with the accelerator, both capped by Amdahl's limit of 1.43 to 2.5.
  Verdict: **custom instruction**. On kernel time alone the assumed accelerator is faster (15 to 38 times the table-driven
  C at 1 KB against 7.2, and faster than the custom instruction from 24 to 80 bytes, or at every size, in all 16
  corners); the verdict rests on the application-level gain, where Amdahl's limit makes the two a near tie, and on what
  is measured: 7 of the accelerator's inputs are assumptions, none of the custom instruction's.

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
  EX while `busy` is high; a finished result is held while the pipeline is stalled; the operands are taken on the
  instruction's first clock in EX and kept, because once EX is held the core's forwarding path may show a stale value;
  an operation killed in EX (by a trap or an interrupt) is left to finish inside the unit and its result dropped, and
  the next instruction waits for it, then starts on its own kept operands;
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

### The wrapper on its own

`hwsw/tests/test_64a_cfu_wrapper_rtl.py` drives the generated wrapper around `crc32_step`, both variants, as a pipeline
would: one instruction at a time, `hold` and `kill` at random (never both in one clock, as the core drives them),
operands right only on the first clock in EX and different on every later clock. A directed test kills an operation
one to four clocks after it starts and issues the next instruction at once: with `byte` that instruction must wait for
the killed operation, then compute on its own first-clock operands. A random soak of 3000 instructions covers kills
before the unit starts, with the operation in flight and with a finished result held; every result taken is checked
against the model. Three seeded faults in the wrapper are each caught: operands not kept, no wait for a killed
operation, and a kill that leaves the unit active.

### Measured in an RV32 core (simulation)

The core is BRV32P (`RISCV_RV32IMC_5stage`, a 5-stage RV32IMC with caches, branch prediction and the Xbrvdsp, Zk, GF
and mod-q extensions). That repository belongs to another project and is read-only here, so a copy pinned
at commit `8d53700` lives in `hwsw/cfu_core/brv32p/` ([PINNED.md](../hwsw/cfu_core/PINNED.md), MIT), and the changes that
wire a unit in are a patch applied to a copy in `build/` ([brv32p_cfu.patch](../hwsw/cfu_core/brv32p_cfu.patch): a
custom-2 decode, the unit instance in EX, its result on the existing extension-unit path, and its `busy` into the
divider's stall input). `python3 hwsw/cfu_core/run_bench.py` compiles one program
([crc_bench.c](../hwsw/cfu_core/bench/crc_bench.c), GCC 13.2, `-O2`) that computes zlib's CRC-32 four ways at four
sizes and checks every result against zlib, and runs it on the pinned core and on the core with each variant, in the
core's own test bench under Icarus Verilog 12. Cycles are counted between two marker instructions, with the caches warmed
by a first call. The baseline core runs the same binary with the custom-instruction calls switched off by one data word,
so the software kernels are at the same addresses everywhere: their cycle counts are identical on all three cores (the
patch changes nothing else). The program also checks two kinds of kill, and a simulation-only monitor in the wrapper
(`CFU_MONITOR`) counts them in the record:

- a misaligned load traps with the custom instruction right behind it in EX. The trap is taken in the instruction's
  first clock in EX, so the kill comes before the unit has started; the handler skips the load and the retried
  instruction returns the right value;
- a timer interrupt, 16 times, part-way through a run of custom instructions. The core takes an interrupt only when EX
  is not stalled, so with a custom instruction in EX it lands in the clock the unit delivers its result: the monitor
  sees the kill with the operation still marked in flight (6 times with `word`, 9 with `byte`; the other interrupts
  landed on other instructions), and the instruction runs again after `mret`. Every CRC still equals zlib's.

A retry that must wait for a killed operation never happens in this core: a trap or interrupt handler takes longer than
the unit's 4-clock latency. That path is tested on the wrapper alone (above).

| Core | Kernel | 16 B | 64 B | 256 B | 1024 B | cycles per byte at 1024 B |
|---|---|---|---|---|---|---|
| pinned core | table-driven C (1 KB table) | 208 | 736 | 2848 | 11296 | 11.03 |
| pinned core | bitwise C (no table) | 1042 | 4066 | 16175 | 64546 | 63.03 |
| pinned core | carry-less multiply (Zbkc, Zbkb) | 81 | 201 | 681 | 2602 | 2.54 |
| with crc32_step `word` (latency 1) | custom instruction crc32.w | 62 | 133 | 422 | 1574 | 1.54 |
| with crc32_step `byte` (latency 4) | custom instruction crc32.w | 74 | 181 | 614 | 2342 | 2.29 |

Speed-up of the custom instruction (cycles of the software kernel / cycles with the instruction, same core):

| Custom instruction | against | 16 B | 64 B | 256 B | 1024 B |
|---|---|---|---|---|---|
| `word` | table-driven C (1 KB table) | 3.35x | 5.53x | 6.75x | 7.18x |
| `word` | carry-less multiply (Zbkc, Zbkb) | 1.31x | 1.51x | 1.61x | 1.65x |
| `byte` | table-driven C (1 KB table) | 2.81x | 4.07x | 4.64x | 4.82x |
| `byte` | carry-less multiply (Zbkc, Zbkb) | 1.09x | 1.11x | 1.11x | 1.11x |

The cycle counts lie on straight lines in the size to within one cycle (fitted on 16 B and 1024 B; the 64 B point is
one cycle under): the `word` instruction costs 38 + 1.5 cycles per byte, that is 6 cycles per word for 5 instructions
(load, two adds, the instruction, the branch) plus one stall clock; `byte` costs 38 + 2.25 cycles per byte, three stall
clocks more per word, exactly its extra latency. The table-driven C costs 32 + 11
cycles per byte. So the low-latency variant is the one to wrap, as the decision skill says.

### What the unit costs the core (Vivado 2026.1)

`python3 hwsw/cfu_core/core_ooc.py` builds the whole SoC (core, caches, 32 KB SRAM, peripherals) out of context on the
xc7a100t at a 10 ns target, once per core, with one place-and-route run each. The clock constraint is read before
synthesis, so synthesis is timing driven. The raw reports (`utilization_hier.rpt`, `timing_summary.rpt`,
`critical_path.rpt`, `summary.txt`) are committed in [results/64a_hwsw/core_ooc/](../results/64a_hwsw/core_ooc/).

| Core | SoC LUTs | SoC FFs | core LUTs | wrapper (LUTs / FFs) | library unit inside it (LUTs / FFs) | DSP | WNS at 10 ns (ns) | Fmax estimate (MHz) |
|---|---|---|---|---|---|---|---|---|
| pinned core | 11854 | 7917 | 8663 | - | - | 16 | -6.123 | 62.0 |
| with crc32_step `word` | 12254 | 8042 | 9034 | 285 / 133 | 283 / 33 | 16 | -5.233 | 65.6 |
| with crc32_step `byte` | 12004 | 8160 | 8811 | 182 / 192 | 179 / 92 | 16 | -6.210 | 61.7 |
| `word`, the unit's hierarchy kept (an experiment) | 12273 | 8043 | 9050 | 295 / 133 | 97 / 33 | 16 | -5.413 | 64.9 |

- **Logic.** With `word` the core grows by 371 LUTs (4.3 %) and 125 flip-flops: the unit, the decode, the wider result
  multiplexer, the stall logic, and the 64 flip-flops that keep the operands. With `byte` it grows by 148 LUTs.
- **Clock rate.** No measured Fmax loss (one run each). The estimates (62.0 MHz without a unit, 65.6 with `word`, 61.7
  with `byte`) differ by run-to-run placement, and the critical path is in the core's fetch, writeback or
  modular-arithmetic logic in every run, never in the unit. The core misses 100 MHz either way: that is the pinned
  core's own figure.
- **Why the unit shows 283 LUTs in the core but 95 out of context.** With its hierarchy kept, so that no logic can move
  across its boundary, the same unit takes 97 LUTs, close to its 95 out of context, and the core grows by about the
  same amount (387 LUTs against 371). So the larger figure is logic of the core (the operand multiplexers in front of
  the unit) that synthesis merged into the unit's XOR network and counted under it, not a bigger unit. One run each.
  The lesson stands in a narrower form: read a function unit's cost as the growth of the whole core, not as the
  unit's line in the hierarchy report.
- **The trade.** `byte` saves 223 LUTs in the core (2.6 %) and costs 0.75 cycles per byte, 49 % more time. The decision
  skill's default, the lowest-latency variant, holds unless the core is short of logic.

### What this does not show

- No board run: the core with the unit has not been built for or run on the Nexys A7 or a Zynq.
- One kernel, one compiler, one core. The cycle counts are for this core's caches and branch predictor at these sizes.
- The stall-based port costs one clock per instruction for a 1-clock unit; completing in MEM, as the core's multiplier
  does, would hide it for independent instructions. Not built.
- The decoder accepts one encoding per generated unit; several units on one opcode need a funct-based selector.
