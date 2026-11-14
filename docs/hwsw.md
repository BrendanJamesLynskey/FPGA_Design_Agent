# HW/SW interface and partitioning

**What this is for.** When a task has a processor part and a hardware part, these tools help decide what goes where,
build the interface between the two, and check it.

**Results in plain words.**
- A CRC-32 unit from the IP library, added to an RV32 5-stage core as one new instruction, runs 7.2 times faster than
  the usual table-driven C (1.54 against 11.0 clock cycles per byte at 1 KB), and 1.65 times faster than the same CRC
  done with the carry-less multiply instructions. It adds 371 LUTs to the core (4.3 % of its 8,663) with no measured loss of clock rate (one build each). Simulation and out-of-context builds only.
- Completing that instruction in MEM, as the core's multiplier does, instead of holding the pipeline in EX saves one
  clock per instruction: 1.29 cycles per byte against 1.54.
- The core we pinned loses an instruction that holds the pipeline in EX when the branch predictor wrongly predicts it
  taken. A directed test shows it; a one-line change in our copy fixes it.
- On a Zynq-7000, with every input an assumption, the cost model cannot say whether a DMA-fed CRC block beats the Arm
  core. It names the one measurement to take first: the Arm's cycles per byte.
- The register-map generator makes the hardware block, the C header, the Python driver and the document from one file,
  and a check proves the four agree. Every register block now has a datasheet that states, from the map's settings,
  each behaviour a driver writer could guess wrong. A read of an unmapped address inside a block answers SLVERR with data
  0 and a write answers OKAY and changes nothing (the split response), and every such access is recorded by two generated
  error-capture registers: the address of the first, a saturating count and a sticky flag.

Three tools for the boundary between a processor and the fabric (briefs 64A, 64A+ and 64A2). Everything here was checked in
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
| `run_bench.py` | `wrote .../results/64a_hwsw/cfu_crc32.json`, after `RESULT PASS` for the baseline and the four patched cores, and the four `stale_btb` lines (one expected `RESULT FAIL`) |
| `pytest` | `N passed` with no failures (the core bench and the formal tests are skipped without their tools) |

## Words used here

| Term | Meaning |
|---|---|
| Register block | the logic that holds a block's control and status registers and answers the CPU's reads and writes |
| AXI4-Lite | Arm's simple memory-mapped bus: one 32-bit read or write at a time, each with a response |
| W1C, W1S, W1P | write 1 to clear, write 1 to set, write 1 to pulse: access types for events, doorbells and commands |
| Doorbell | a register write that tells the hardware new work is ready |
| MEM, WB | the memory and write-back stages, after EX; the core's multiplier completes in MEM, and WB writes the register file |
| Mispredict, flush | the branch predictor guessed wrong; the core redirects fetch and discards (flushes) the wrong-path instructions |
| OKAY, SLVERR, DECERR | AXI responses: success; an error from the addressed block; an error from the interconnect because no block owns the address |
| Snapshot group | registers that together hold a value wider than 32 bits; a write to its trigger copies the whole value into shadow registers (copies) in one clock, and reads return the copy |
| Use hazard | a clock the pipeline waits because the next instruction needs a result that is not ready yet (as after a load) |
| BTB | branch target buffer: the branch predictor's table of addresses where a taken branch was seen, and where it went |
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
profile: house              # optional: house (default) | amd_compatible | strict; see "Interface profiles". The settings below override it
name: demo_accel            # lower case; the module is demo_accel_regs, the C prefix DEMO_ACCEL_
version: 0.1.0
addr_width: 12              # a 4 KB window (only address bits [11:2] are decoded)
unmapped: split             # the default: a read of a hole answers SLVERR, a write OKAY; or okay, or slverr (both channels)
error_capture: true         # the default: ERR_ADDR and ERR_STATUS in the top two words; false leaves them out
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
  - {name: SNAP, lsb: 2, width: 1, access: W1P}
- name: JOB_CYCLES_LO
  offset: 0x030
  fields:
  - {name: VALUE, lsb: 0, width: 32, access: RO}
- name: JOB_CYCLES_HI
  offset: 0x034
  fields:
  - {name: VALUE, lsb: 0, width: 32, access: RO}
snapshot:                   # a value wider than the bus, read consistently
- {name: JOB_CYCLES, trigger: CMD.SNAP, fields: [JOB_CYCLES_LO.VALUE, JOB_CYCLES_HI.VALUE]}   # low part first
```

| Access | Software | Hardware port |
|---|---|---|
| `RW` | reads and writes the value | `<reg>_<field>_o` |
| `RO` | reads; writes are ignored | `<reg>_<field>_i`, or a constant with `const:` |
| `W1C` | writing 1 clears a bit; a hardware set in the same clock wins | `<reg>_<field>_set_i` (pulse), `_o` (value) |
| `W1S` | writing 1 sets a bit; it wins over a hardware clear in the same clock | `<reg>_<field>_clr_i` (pulse), `_o` (value) |
| `W1P` | writing 1 gives a one-clock pulse; reads 0 | `<reg>_<field>_pulse_o` |

### House conventions (owner, 2026-11-13)

Every generated block follows these unless its design chose another profile (next section), and its generated document states each one in a Behaviour section, written from
the map's settings (`behaviour()` in `hwsw/regmap.py`; `hwsw/tests/test_64a_regmap.py` checks that each sentence
follows its setting). A hand-written block's datasheet (the "Registers" section of an `ip_lib` README) states the same
topics, and says in its first paragraph where the block differs from these conventions.

- **Unmapped addresses inside a block use the split response** (`unmapped: split`, the default; owner, 2026-11-13): a
  read of a hole answers SLVERR with data 0, and a write to a hole answers OKAY and changes nothing. The owner's reasons,
  as decided: a stray read shows up at bring-up (on an Arm CPU a SLVERR on a load is expected to be reported at the load
  itself, as a synchronous external abort), while a write is posted, and a SLVERR on a posted write is expected to reach
  the CPU late and imprecisely, which is hard to attribute. **Both statements are expectations from Arm documentation;
  the behaviour of the project's Arm platforms has not been measured yet**: brief 64B item 5 measures it, and until
  then the generated datasheets say "expected", not "does". `unmapped: okay` (OKAY and read 0 for both) and
  `unmapped: slverr` (SLVERR for both) stay as options, so every choice remains available. Addresses outside every
  block's range are the interconnect's: `ip_lib/axil_xbar` answers DECERR there, and the block-design address map
  (`gen/address_map.md`) lists those holes. In the generated RTL the response is two constants,
  `RESP_UNMAPPED_RD` and `RESP_UNMAPPED_WR`.
- **Error capture** (`error_capture:`, on by default): because the write is quiet, the block records every access to an
  unmapped address, whatever the response setting. Two registers, by default the top two words of the window (give
  `error_capture: {offset: 0x...}` for another place; the offset is ERR_ADDR's and ERR_STATUS is the next word; the loader
  refuses a map whose registers overlap them, and refuses user registers named `ERR_ADDR` or `ERR_STATUS`):
  - `ERR_ADDR.ADDR`: the word-aligned address, inside the window, of the first bad access since the last clear;
  - `ERR_STATUS.STICKY` (W1C): set by a bad access; write 1 to clear the record; `IS_WRITE` (RO): the recorded access
    was a write; `COUNT` (RO, bits 15:8): bad accesses since the last clear, saturating at 255; `IRQ_EN` (RW, bit 2,
    only with `error_capture: {interrupt: true}`): `irq_o` is high while STICKY and IRQ_EN are both 1 (ORed with the
    block's own interrupt, if it has one). The interrupt is off by default.
  - Later bad accesses do not replace the recorded one. A clear (STICKY and COUNT go to 0) leaves ERR_ADDR and IS_WRITE
    as they were; they mean something only while STICKY is 1. Same-clock priority is the house convention: a bad access in
    the very clock of the clear wins and starts the new record (STICKY 1, COUNT 1); a bad read and a bad write in the
    same clock count 2 and the read is the one recorded. A clear needs the strobe of byte 0. Reads of the capture registers
    have no side effect, and a write to their read-only bits is ignored with OKAY.
  - `error_capture: false` leaves the registers out, and the datasheet then says so in its first paragraph, as a
    difference from the house conventions.
  The cost is in [results/64a_hwsw/regmap_ooc_split.json](../results/64a_hwsw/regmap_ooc_split.json) (Vivado 2026.1, xc7a100t, 10 ns, one run each, the example block alone with its registers: `okay` 180 LUTs and 241 flip-flops, `slverr` 181 and 243, `split` 183 and 242, and `split` with the error capture 248 and 262. The split response costs 3 LUTs and 1 flip-flop over `okay`; the capture is not a few LUTs: it adds 65 LUTs and 20 flip-flops, about a third more than the rest of this small block, which is why `error_capture: false` exists. Re-run with `python3 hwsw/regmap_ooc.py`).
- **Reads have no side effects.** There is no clear-on-read or pop-on-read type: the loader refuses an access type
  that would change state on a read (`RC`, `RS`, `POP` and the like) and an `on_read:` key. To pop a FIFO or
  acknowledge something, write 1 to a W1P bit. A read with a side effect breaks debuggers, repeated or speculative
  reads, and read-modify-write (the knowledge-bank skill `register-maps-for-software` gives the rules).
- **Same-clock priority:** a hardware set beats a software W1C clear in the same clock (the event is not lost), and a
  software W1S set beats a hardware clear in the same clock (the doorbell is not lost). The bench checks both, timed
  to the commit clock: `set_beats_clear_in_the_same_clock` in `hwsw/tests/regmap_cocotb.py`, with two seeded faults
  (`clear_beats_set`, `w1s_lost`) that it catches.
- **Values wider than the bus use a snapshot group.** A `snapshot:` entry names a one-bit W1P trigger and the RO
  fields of the value, low part first (at most 64 bits). Writing the trigger copies every part into shadow registers in
  the same clock; reads of those fields return the copy, so the parts always belong to one instant. A read without a
  new snapshot returns the last copy (stale), and the document says so. The C header gets a helper
  (`demo_accel_snapshot_job_cycles(base)`) and the Python driver `snapshot("JOB_CYCLES")`.
- **Byte strobes are honoured; access is 32-bit**; address bits [1:0] are not decoded (house; `strict` rejects what it cannot take as asked, see the profiles).
- **Reset is `aresetn`, synchronous, active low**; every stored field has a reset value; RO fields read their input.
- **The interrupt** `irq_o` is a level output from a register: high while any status bit is set together with its
  enable bit, one clock after the cause; a W1C clear drops it one clock later.
- **Every register block has a datasheet** that states all of the above, generated, not written by hand: the
  generated `<name>_regs.md` for a generated block, and for a hand-written `ip_lib` entry with an AXI4-Lite slave port
  a "Registers" section in its README, made by `flow/net/ipdoc.py` from a `register_map:` in its `ip.yaml` (a
  documentation-only map: `WO` registers, `count:`, `conventions:` and `staging:` are allowed there and nowhere else).
  A hand-written block's datasheet states every topic as the block behaves, with its differences first; the block-design
  address map states only how the generated register banks differ. `ipdoc.py --check` fails for an entry with such a
  port and no section; `register_map: {none: <why>}` covers a block
  with no registers of its own (`axil_xbar`). `axil_table_ctrl`'s datasheet opens with its four differences: unmapped
  addresses answer OKAY and read 0 (house: the split response), no error capture, byte strobes ignored, and the reset
  `rst`, active high. The test shell answers BAD_ADDRESS with data 0 for its reserved
  addresses, which `shell/PROTOCOL.md` already states.

The loader refuses, with every reason listed: overlapping registers or fields, offsets that are not word-aligned or
fall outside the window, reset or constant values wider than their field, unknown access types or keys, a reset on a
hardware input, a W1P reset other than 0, a read side effect, duplicate names, generated port names that collide, names that clash with
the generated register-level names, two registers whose C names would meet, an interrupt status register with non-W1C fields or bits without an enable,
a snapshot whose trigger is not a one-bit W1P field, whose parts are not RO hardware inputs, are in another group, or
exceed 64 bits,
register names the block uses for its own signals (`HIT`, `COMMIT`, `VALUE`: `wr_hit`, `wr_commit`, `rd_value`), and
an unknown profile or setting value, a strict profile with the two halves of a wide value (`NAME_LO`/`NAME_HI` and the other
recognised pairs) read outside a snapshot group, a profile in a documentation-only map, and text that would break an output: a newline or other control character, `*/`, `/*`, `"""`, a backslash or `|` in a
summary, or a version that is not letters, digits and `. + _ -`. `gen` checks the text again before it writes.

### Interface profiles (brief 73)

A **profile** is a named bundle of the settings of a register block. `house` is the default and is the convention set
described above; `amd_compatible` and `strict` are the other two. A design chooses one once, in `spec.yaml`, and may
override it per block and per setting:

```yaml
interfaces:
  axi_lite_profile: house          # house | amd_compatible | strict; the design's default
  blocks:                          # optional: one entry per register map, by the map's name
    demo_accel: {profile: strict, unmapped: okay}     # a block's profile, and single settings of it
  amd_ip_acknowledged: [axi_gpio]  # AMD IP the design uses beside a strict block; see "The check"
```

A map names no profile of its own unless it wants to (`profile: strict` at the top of the regmap YAML), and each of its
settings can be given by name (`unmapped:`, `error_capture:`, `partial_write:`, `unaligned:`, `reserved_write:`,
`wide_values:`). **Resolution, most specific first:** the map's own setting, the map's own profile, the design's entry for
the block (`interfaces.blocks.<name>`: its settings, then its profile), the design's `axi_lite_profile`, `house`. A map
that names its own profile is not changed by the design's block entry (the `axi_profile` check reports the
disagreement). `python3 -m hwsw.regmap gen|check <map>.yaml --spec designs/<d>/spec.yaml` applies the design's choice;
without `--spec` a map that names no profile is `house`. The datasheet names the profile and lists every setting that
differs from it. Maps that name no profile and no new setting generate the same model hash as before profiles existed.

| Setting | `house` (default) | `amd_compatible` | `strict` |
|---|---|---|---|
| `unmapped`: a hole inside the block | SLVERR on read, OKAY on write (`split`) | OKAY and read 0 (`okay`) | SLVERR on read and write (`slverr`) |
| `error_capture` | on | off (no registers take address space) | on, with the interrupt (`on+irq`) |
| `partial_write`: strobes cover part of a multi-byte field | accepted (`accept`) | accepted | SLVERR, nothing changes (`slverr`) |
| `unaligned`: address bits [1:0] not 0 | not decoded: reaches the word (`ignore`) | not decoded | SLVERR (`slverr`) |
| `reserved_write`: a 1 written to a reserved bit | ignored (`ignore`) | ignored | SLVERR, nothing changes (`slverr`) |
| `wide_values` | a snapshot group is available (`optional`) | available | required for the LO/HI pairs the generator recognises (`snapshot`) |
| Reserved bits read | 0 | 0 | 0 |
| Read side effects | none (W1P pops) | none | none |
| W1C/W1S same-clock priority | the hardware event wins | the hardware event wins | the hardware event wins |
| Byte strobes | honoured | honoured | honoured |
| Interrupt output | level, registered | level | level |
| Outstanding transactions | one per direction | one per direction | one per direction |

The last six rows are the same in every profile; no profile can change them. **`amd_compatible` means driver-visible
compatibility, never copied defects.** It copies only what a driver written for AMD IP can rely on, as measured in
[brief 69](../results/69_amd_ip_conventions/README.md): a hole answers OKAY and reads 0, and no error-capture registers
take address space. It does not copy what brief 69 found to be defects or hazards: registers that alias, a lost event in
a same-clock race, a 64-bit read that tears, a read that pops or clears, a lost write response, or ignored byte strobes
(honouring them cannot break a driver that writes whole words).

What a user could guess wrong in the strict settings, each stated in the generated datasheet:

- **`partial_write: slverr`.** AXI4-Lite has no transfer size, so a CPU's byte or halfword store arrives as a word write
  with fewer strobes. A write is rejected when its strobes cover some but not all byte lanes of a **writable field that
  spans more than one lane** (a 12-bit field over lanes 2 and 3 with only lane 2 strobed, for example). The whole write
  is rejected: SLVERR and no field of the register changes, not even the ones the strobes cover wholly. A write that
  covers every lane of such a field, or none of its lanes, is accepted; so is any strobe pattern on a field inside one
  byte lane; a write with all strobes 0 changes nothing and answers OKAY. Only RW, W1C, W1S and W1P fields count (a
  strobe pattern over a read-only field is ignored as before).
- **`unaligned: slverr`.** AXI4-Lite reads cannot be narrow, so this is only the address: bits [1:0] not 0 answer SLVERR
  to a read (data 0) and to a write (nothing changes), whatever the word would be, an unmapped one included.
- **`reserved_write: slverr`.** A write that has a 1 in a reserved bit (a bit that belongs to no field of that register),
  in a byte lane whose strobe is 1, answers SLVERR and changes nothing at all. Reserved bits still read 0, so writing
  back what was read is safe; the error-capture and read-only registers have reserved bits too (a write of all ones to
  ERR_ADDR is rejected, not ignored).
- **Error capture records every rejected access**, not only unmapped ones, because it is the one place a bring-up
  engineer looks; it does not say which cause (a follow-up could add a cause field). The interrupt is on in `strict`.
- **`wide_values: snapshot`.** The generator cannot see which registers form one value, so it recognises the naming
  pairs `NAME_LO`/`NAME_HI`, `_LOW`/`_HIGH`, `_LSW`/`_MSW`, `_L`/`_H`: every hardware-input field of such a pair must be in
  a snapshot group, or the map is refused with the way out (`wide_values: optional`). A wide value named another way is
  the author's to put in a group; the profile cannot enforce it.

**The check.** The `check` tool's `axi_profile` check (`flow/checks/axi_profile.py`; rules `HDL-IF-04` to `HDL-IF-06`)
does not trust a block's `// PROFILE` claim. For every generated `*_regs.sv` in the design it finds the block's source
map, resolves the profile as above under the design's `interfaces:`, regenerates the RTL and compares it with the file:
a block that claims `strict` and behaves as `house` fails (`AXI-PROFILE-DRIFT`), as does a file with a `// PROFILE` line and
no generator banner; a block generated under another profile than its design declares fails (`AXI-PROFILE-MISMATCH`); a
setting the block has that its profile (plus the design's `blocks:` entry) does not give it fails (`AXI-PROFILE-OVERRIDE`:
a map's own `partial_write: accept` in a strict design must be declared as `interfaces.blocks.<name>.partial_write`, and a
map that names its own profile ignores the design's block settings); a block with no `// PROFILE` line (`AXI-PROFILE-STALE`)
or no source map (`AXI-PROFILE-NOSRC`) fails because its claim cannot be compared; an invalid or unparseable `interfaces:`
section, or a `blocks:` key naming no block, fails (`AXI-PROFILE-SPEC`). Every `.sv` or `.v` file of the design is scanned,
whatever it is called. It flags, without failing: a map that names its own profile in a design that chose none (with a
design profile chosen it fails, `AXI-PROFILE-MIX`), and AMD IP of brief 69's list in a design with a strict block or
a strict design profile unless listed under `amd_ip_acknowledged` (`AXI-PROFILE-AMD-STRICT`: those blocks answer a hole
with OKAY and ignore strobes, so a strict driver's expectations do not hold for them). It does not read hand-written blocks (their conventions are in their `ip.yaml`), and it cannot see an
interconnect between a strict master and an AMD slave: the AMD rule is by presence in the design.

**Cost** (Vivado 2026.1, xc7a100t, 10 ns, out of context, the same map under each profile, one run each,
[results/73_profiles](../results/73_profiles/README.md)):

| Profile | LUTs | Flip-flops | WNS at 10 ns |
|---|---|---|---|
| `house` | 248 | 262 | 5.147 ns |
| `amd_compatible` | 180 (68 fewer: no capture registers) | 241 (21 fewer) | 5.634 ns |
| `strict` | 286 (38 more) | 266 (4 more) | 2.567 ns |

The strict block's slack is 2.6 ns smaller (probably the rejection tests in front of the register write strobes; not
investigated) and it still closes at 10 ns. The `amd_compatible` figures reproduce brief 64A3's `okay` build, `house` its `split` with the capture.

**What would carry over to other interfaces.** The mechanism (a named bundle of settings, one choice per design with
per-block overrides, a datasheet that lists the differences, and a check that regenerates and compares) does not depend on
AXI4-Lite. A later profile for AXI4-Stream would reuse `interfaces:` with its own key, the same resolution order and the
same check shape; its settings (what `TKEEP`/`TSTRB` mean, `TLAST` rules, back-pressure on `TREADY`) belong to its own
convention brief. Resets are not a profile: they are synchronous, by owner decision.

### What is generated

| Output | What it holds |
|---|---|
| `<name>_regs.sv` | the AXI4-Lite slave (AW and W captured independently in either order, byte strobes honoured bit by bit, one outstanding read and write, synchronous active-low reset), the field storage, the snapshot copies and the read multiplexer, `ADDR_` and `RESET_` constants |
| `<name>_regs.h` | per register `_OFFSET`, `_RESET` and a mask per access type (`_RW_MASK` is the read-modify-write mask); per field `_SHIFT`, `_WIDTH`, `_MASK`, `_RESET`, `_ACCESS`; `GET`/`PUT` macros and read and write functions whose bus access can be replaced before the header is included |
| `<name>_regs.py` | the table, a blocking driver and the same driver for a bus whose calls are coroutines (a simulation bus), and a memory-mapped bus for a UIO device or `/dev/mem`; `set` keeps the other RW fields and writes W1C, W1S and W1P bits as 0, so it never clears an event by accident |
| `<name>_regs.md` | the datasheet: the map, the access types, a Behaviour section (unmapped and reserved accesses, read side effects, same-clock priority, partial writes, access width and alignment, wide values, reset, the interrupt, clock domain and timing), each register's fields, the snapshot groups and the hardware ports |

All four carry the SHA-256 of the map's content, so a stale output is easy to spot.

### How agreement is checked

`python3 -m hwsw.regmap check <map.yaml>` does two things:

- **Drift:** every output is regenerated and compared with the file on disk; a hand edit or a changed YAML fails.
- **Agreement:** each output is read back on its own terms and compared with the YAML: the C header by compiling a probe
  program that prints every generated constant; the Python driver by importing it; the markdown by parsing its tables;
  the SystemVerilog by its port list and its address and reset constants, and by compiling it with Icarus Verilog
  (`iverilog -g2012`) when that is installed.

`hwsw/tests/test_64a_regmap.py` edits each output by hand in 17 ways (a mask, a reset, an access type, an offset, a port
width, a snapshot group) and checks that the agreement check names each one, and breaks 53 rules of the format (among them the error-capture clash, reserved names and bad settings) and
checks that the loader refuses each.

### How the generated RTL is verified

`hwsw/tests/test_64a_regmap_rtl.py` simulates four maps under cocotb (and, since brief 73, the demo map under each of the three profiles, below) and Icarus Verilog 12: the example `demo_accel`
(13 registers of its own, every access type, an interrupt, a 64-bit snapshot group, the split response, the error capture
at its default place), a map of awkward layouts (fields across byte lanes, a 32-bit field, multi-bit W1C, W1S and W1P
fields, a register at the top of a 64-byte window, SLVERR for both channels, the error capture with its interrupt at an
explicit offset), and two small blocks with the okay setting, one with the error capture at the default place of a
32-byte window and one with it left out; so all three unmapped settings are simulated. The
bench reaches the RTL only through the **generated Python driver** over an AXI4-Lite master with random VALID delays, a
random order of AW and W, and random BREADY and RREADY back-pressure. The brief 59A AXI4-Lite protocol checker
(`axi_tx/rtl/axil_checker.sv`) watches the same wires and fails the test on any rule. Tests:

- every register's reset value, and every stored field's output after reset;
- each access type, field by field, through the driver's own calls (`set`, `clear`, `ring`, `pulse`), with the hardware
  ports checked and the W1P pulses counted;
- the same-clock races: a hardware set during a W1C clear, and a hardware clear during a W1S ring, both timed to the
  commit clock;
- 8 random byte-strobe writes per register against a model built from the YAML alone;
- unmapped addresses (all of them in the small maps, 64 sampled in the 4 KB one): the response of a read and of a write
  separately, read value, no side effect, and the capture registers afterwards (first address, read or write, count);
- the error capture: the first bad access is kept and a later one only counted, an unaligned address is recorded
  word-aligned, the count saturates at 255 (300 bad reads), reads of the capture have no side effect, writes to its
  read-only bits and a clear without byte 0's strobe change nothing, a clear leaves the next bad write recorded as a
  write, and the capture's interrupt follows STICKY and IRQ_EN;
- the capture's same-clock races, timed to the commit clock of the clearing write: a bad read in that clock starts the
  new record instead of being lost, and a bad read plus a bad write in one clock count 2 with the read recorded;
- the snapshot group: the bench drives JOB_CYCLES as a counter that steps every clock, starting just below the carry
  out of the low half, and sweeps the start over 39 snapshots so that at least one lands on the all-ones clock; every
  snapshot must read a value the counter really had during the access, and a second read without a snapshot must
  return the same (stale) value;
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
  jobs, then reads JOB_CYCLES (counted across a carry into the high half) through the generated snapshot helper. The
  same driver source compiles for the Cortex-A9 with `arm-none-eabi-gcc -mcpu=cortex-a9`.

The same bench runs on the demo map under each interface profile (`hwsw/examples/profiles/spec_<profile>.yaml` as the
design's choice), with the reference model taking each profile's rejections from the resolved settings, and one more test,
`profile_settings`, exercises every setting in the direction the map has it: an unaligned read and write (SLVERR, data 0,
nothing changes, the capture counts them), every strobe pattern over each multi-byte RW field (rejected unless all or none
of the field's lanes are strobed, and a rejected write leaves the other fields alone), a 1 written to a reserved bit (rejected,
and accepted when its byte lane is not strobed). Eleven seeded faults in the strict RTL must each fail it: an unaligned write
accepted or answered OKAY, an unaligned read answered OKAY or returning data, a partial write accepted, a rejected write that
still applies or answers OKAY, a reserved-bit write accepted, a reserved-bit check that ignores the strobes, and the capture
missing a rejected write or an unaligned read. Brief 71's missing-response monitor (`axi_tx/rtl/axil_resp_rules.sv`) is on the
wires of this bench and of the b65a bench; a response that never comes fails the test.

Twenty-two seeded faults in the generated RTL must each fail the bench; all twenty-two do. Eight are earlier: a clear that beats
a set, byte strobes ignored, B before W, a lost doorbell, an interrupt that ignores its enable, a pulse that stays high,
ARREADY high while a read response waits, a snapshot whose high half loads one clock after its low half. Six give the
wrong response to an unmapped address: for each of the split, okay and slverr maps, one fault on the read response and
one on the write response. Eight are in the error capture: a clear that ignores the byte-0 strobe, a clear that keeps the count, it keeps the last bad access instead of the first, a clear in
the clock of a bad access loses that access, the count wraps instead of saturating, a bad write is recorded as a read,
a bad write beats a bad read in the same clock, and the capture's interrupt ignores its enable. The B-before-W fault is caught by the protocol checker (rule 5, B_EARLY).

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
- with `--style mem`, `cfu_crc32_step.sv` is instead the **MEM-completion** port, the way the BRV32P multiplier works:
  `issue` (the instruction moves from EX to MEM this clock, operands on `a` and `b`), `in_mem` and `hold` in; `stall`
  (hold MEM: the result is not ready) and `result` out. The core issues only in a clock in which EX moves on and no
  trap flushes the instruction, so an issued instruction always completes and there is no kill; the core's hazard unit
  holds a dependent next instruction for one clock, as after a load; a unit of latency L holds MEM for L - 1 clocks; a
  result that arrives while MEM is held by a cache miss is kept until the instruction leaves;
- `cfu_ops.vh`: the module name and the encodings the core's decoder accepts (anything else stays illegal);
- `cfu_crc32_step.h`: `crc32_w(rs1, rs2)` for C, written with the GNU assembler's `.insn` directive (R-type, custom-2
  opcode `0x5b`), so no compiler change is needed.

### The first entry: `crc32_step`

[ip_lib/crc32_step](../ip_lib/crc32_step/README.md) is one CRC-32 update (IEEE 802.3, reflected) by a 32-bit word: two
operands, one result, no state; the running CRC lives in a register between calls. Two variants: `word` (the whole
update in one clock, latency 1) and `byte` (one byte per clock, latency 4). Both are bit-exact against `model.py` and
against zlib over whole buffers, with latency and II measured; five seeded faults are each caught. Measured out of
context with Vivado 2026.1 on the xc7a100t: `word` 95 LUTs and 33 flip-flops, `byte` 96 LUTs and 92 flip-flops. Alone
the two look the same size, but inside the core in the 64A run (below) `byte` grows it by 148 LUTs against 371 for
`word` (one run each; 105 against 432 in the 64A2 rebuild), at 2.29
against 1.54 cycles per byte: an area-for-speed option, kept for that.

### The wrapper on its own

`hwsw/tests/test_64a_cfu_wrapper_rtl.py` drives the generated wrapper around `crc32_step`, both variants, as a pipeline
would: one instruction at a time, `hold` and `kill` at random (never both in one clock, as the core drives them),
operands right only on the first clock in EX and different on every later clock. A directed test kills an operation
one to four clocks after it starts and issues the next instruction at once: with `byte` that instruction must wait for
the killed operation, then compute on its own first-clock operands. A random soak of 3000 instructions covers kills
before the unit starts, with the operation in flight and with a finished result held; every result taken is checked
against the model. Three seeded faults in the wrapper are each caught: operands not kept, no wait for a killed
operation, and a kill that leaves the unit active.

The MEM-completion wrapper has its own bench (`hwsw/tests/cfu_mem_wrapper_cocotb.py`), which plays EX and MEM: an
instruction leaves EX only in a clock in which MEM is not held, back to back or with gaps; other MEM stalls (`hold`)
come at random, so results also arrive while MEM is held; operands are right only in the issue clock. The directed test
checks that the unit holds MEM for exactly latency - 1 clocks per instruction (0 for `word`, 3 for `byte`), and a soak
of 3000 instructions checks every result. Two seeded faults are each caught: a stall that never comes (the result taken
early) and a kept result that is not cleared when the instruction leaves. A third (dropping the kept copy) cannot be
seen with `crc32_step`, whose output register holds its value until the next issue; the copy is there for units whose
result is valid only with the done pulse, which is all the function-unit contract promises.

### Measured in an RV32 core (simulation)

The core is BRV32P (`RISCV_RV32IMC_5stage`, a 5-stage RV32IMC with caches, branch prediction and the Xbrvdsp, Zk, GF
and mod-q extensions). That repository belongs to another project and is read-only here, so a copy pinned
at commit `8d53700` lives in `hwsw/cfu_core/brv32p/` ([PINNED.md](../hwsw/cfu_core/PINNED.md), MIT), and the changes that
wire a unit in are patches applied to a copy in `build/`, one per integration style (owner, 2026-11-13: "try both"):

- **stall in EX** ([brv32p_cfu.patch](../hwsw/cfu_core/brv32p_cfu.patch)): a custom-2 decode, the unit instance in EX,
  its result on the existing extension-unit path, and its `busy` into the divider's stall input;
- **complete in MEM** ([brv32p_cfu_mem.patch](../hwsw/cfu_core/brv32p_cfu_mem.patch)): the same decode; the unit issued
  as the instruction leaves EX and its result taken in MEM next to the multiplier's, its `stall` added to the memory
  stall, and the custom instruction added to the hazard unit's multiply-use hazard, so a dependent next instruction
  waits one clock and takes the value from WB;
- both also get [brv32p_mispredict_hold.patch](../hwsw/cfu_core/brv32p_mispredict_hold.patch) (see "A mispredict
  while EX is stalled", below).

`python3 hwsw/cfu_core/run_bench.py` compiles one program
([crc_bench.c](../hwsw/cfu_core/bench/crc_bench.c), GCC 13.2, `-O2`) that computes zlib's CRC-32 four ways at four
sizes and checks every result against zlib, and runs it on the pinned core and on the core with each variant in each
style, in the core's own test bench under Icarus Verilog 12. Cycles are counted between two marker instructions, with the caches warmed
by a first call. The baseline core runs the same binary with the custom-instruction calls switched off by one data word,
so the software kernels are at the same addresses everywhere: their cycle counts are identical on all five cores (the
patches change nothing else). The program also checks two kinds of kill, and in the EX style a simulation-only monitor
in the wrapper (`CFU_MONITOR`) counts them in the record (the MEM style has no kill path, and passes the same program):

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
| with crc32_step `word` (latency 1), stall in EX | custom instruction crc32.w | 62 | 133 | 422 | 1574 | 1.54 |
| with crc32_step `byte` (latency 4), stall in EX | custom instruction crc32.w | 74 | 181 | 614 | 2342 | 2.29 |
| with crc32_step `word` (latency 1), complete in MEM | custom instruction crc32.w | 58 | 117 | 358 | 1318 | 1.29 |
| with crc32_step `byte` (latency 4), complete in MEM | custom instruction crc32.w | 70 | 165 | 550 | 2086 | 2.04 |

Speed-up of the custom instruction (cycles of the software kernel / cycles with the instruction, same core):

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

The cycle counts lie on straight lines in the size to within one cycle (fitted on 16 B and 1024 B; the 64 B point is
one cycle under): the `word` instruction costs 38 + 1.5 cycles per byte, that is 6 cycles per word for 5 instructions
(load, two adds, the instruction, the branch) plus one stall clock; `byte` costs 38 + 2.25 cycles per byte, three stall
clocks more per word, exactly its extra latency. Completing in MEM saves exactly one clock per instruction in both
variants: 38 + 1.25 cycles per byte for `word` (5 cycles per word, no stall) and 38 + 2 for `byte` (three stall clocks
per word, now in MEM). The use hazard never costs anything in this loop: the next `crc32.w` that reads the result is
four instructions later, and the final inversion two. The table-driven C costs 32 + 11 cycles per byte. So the
low-latency variant is the one to wrap, as the decision skill says, and completing in MEM is worth one clock per
instruction whenever the next instruction does not need the result at once.

### A mispredict while EX is stalled

The pinned core acts on a branch mispredict in EX without checking whether EX is stalled (`branch_mispredict_ex` in
`brv32p_core.v` at commit 8d53700). With a divider or an EX-stall custom instruction in EX that the branch
predictor predicts taken (from a stale BTB entry: one left over from an earlier instruction at the same address), the
mispredict fires in the instruction's first EX clock: it flushes that instruction itself
(`flush_ex`, which also kills the unit) and redirects fetch past it, so the instruction never completes. A non-branch is
predicted taken only through a stale BTB entry (the BTB has full tags), so ordinary code never meets it, and the CRC
benchmark does not. A directed program does: [bench/stale_btb.c](../hwsw/cfu_core/bench/stale_btb.c) trains a taken
branch at an address, writes a custom instruction over it, runs `fence.i` (the predictor keeps its entry) and checks
the instruction's result. `run_bench.py` runs it on four cores (`word` variant):

| Core | stale-prediction program |
|---|---|
| stall in EX, pinned core's mispredict logic | RESULT FAIL (the instruction is lost; its register keeps the old value) |
| stall in EX, with the hold patch | RESULT PASS |
| complete in MEM, pinned core's mispredict logic | RESULT PASS |
| complete in MEM, with the hold patch | RESULT PASS |

The fix, in our pinned copy only ([brv32p_mispredict_hold.patch](../hwsw/cfu_core/brv32p_mispredict_hold.patch)),
gates the mispredict with `!stall_ex`, so it acts in the clock the instruction leaves EX, as the core already does for a
memory stall. The MEM style never stalls EX, so it cannot meet the case. By reading the RTL the pinned core's own
divider has the same exposure; that is not simulated, so unconfirmed. The patch covers it too in our patched copies, and
it changes no cycle count on the CRC benchmark (the EX-style numbers above, 1.54 and 2.29, are with it, equal to 64A's); the core's own repository
is another project's and is not changed here.

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
- **The trade (64A run).** `byte` saves 223 LUTs in the core (2.6 %) and costs 0.75 cycles per byte, 49 % more time. The decision
  skill's default, the lowest-latency variant, holds unless the core is short of logic.

### The two integration styles side by side (Vivado 2026.1)

The 64A table above was built before brief 64A2. For the comparison, all four patched cores were rebuilt with the
mispredict hold patch (`python3 hwsw/cfu_core/core_ooc.py --configs cfu_word,cfu_byte,cfu_word_mem,cfu_byte_mem --out
results/64a_hwsw/core_ooc_styles.json --raw results/64a_hwsw/core_ooc_styles`; the baseline is the 64A pinned core,
without the hold patch, so each growth figure includes the patch's gate). Same flow, one place-and-route run each:

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

- **Speed:** completing in MEM is one clock per instruction faster in both variants (simulation, above).
- **Logic:** with `word` the MEM style grew the core by 193 LUTs against 432 for the EX style in these runs. Part of
  that is structural: the MEM style needs no operand latch (64 flip-flops fewer; it reads the operands the EX/MEM
  register takes) and no EX stall path. The size of the saving is not settled: the EX-style `word` core grew by 371
  LUTs in the 64A run and by 432 here; the two builds differ by the one-gate hold patch and by the run, and one build
  each cannot separate the two. With `byte` the two styles are within 11 LUTs.
- **Clock rate:** the Fmax estimates lie within the spread of single runs in both styles (60.8 to 66.0 MHz against
  62.0 for the pinned core; the EX-style `word` core gave 65.6 and 66.0 in two builds), one run each; the MEM-style
  `word` build is 3 MHz below the EX-style one, which one run each cannot call a loss or not. The critical path is in
  the core's fetch logic in all four runs, never in the unit. The unit's hierarchy line (905 LUTs for `word`
  in MEM style) again includes core logic that synthesis merged into it; read the cost as the core's growth.
- **Verdict for this core:** complete in MEM. It is faster in cycles (simulation) and, in these builds, not larger;
  its only cost, a one-clock use hazard for a dependent next instruction, is never paid in this kernel.

### What this does not show

- No board run: the core with the unit has not been built for or run on the Nexys A7 or a Zynq.
- One kernel, one compiler, one core. The cycle counts are for this core's caches and branch predictor at these sizes.
- The use hazard of the MEM style is never paid in this benchmark (the dependent instruction is four instructions
  later); a kernel that uses each result at once would pay one clock per instruction, as the EX style does.
- The decoder accepts one encoding per generated unit; several units on one opcode need a funct-based selector.
