# sg_dma 0.1.0

scatter-gather DMA engine between an AXI4 memory-mapped master and one AXI4-Stream port: a ring of 16-byte descriptors in memory, an AXI4-Lite control port, INCR bursts that never cross a 4 KB boundary, several bursts in flight, status written back into the descriptor, interrupt coalescing. DIR selects memory to stream (0) or stream to memory (1).

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

**Verification: not assessed: no requirements recorded (no verif/testplan.yaml), so nothing here is traced to a requirement.** [VERIFIED.md](VERIFIED.md) is the generated, hash-pinned record; [what the label means](../../docs/verified.md).

Status: simulated at ten (direction, width, burst, outstanding) points against a memory model with back pressure, SLVERR and DECERR windows and an AXI rule monitor (cocotb, Icarus Verilog 14); the AXI hold rules, the 4 KB rule, burst size and alignment proved by k-induction at 32, 64 and 128 bits (SymbiYosys, slang), burst bookkeeping proved to depth 40; 22 of 22 seeded faults caught; out-of-context Vivado 2026.1 cost on xck26 and xc7z020 (about 570-640 LUTs, 285 MHz and more on the K26, near 100 MHz on the Zynq-7000); not run on a board.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `ADDR_W` | 32 | 32..64 | memory address width in bits |
| `DATA_W` | 32 | 32, 64, 128 | memory and stream data width in bits |
| `MAX_BURST` | 16 | 1..256 | most beats in one burst (also cut at every 4 KB boundary) |
| `OUTSTANDING` | 4 | 1..16 | data bursts addressed ahead of their data (MM2S) or of their response (S2MM) |
| `DIR` | 0 | 0, 1 | 0 memory to stream (MM2S), 1 stream to memory (S2MM) |
| `AXCACHE` | 3 | 0..15 | value of ARCACHE and AWCACHE on every transaction (0011 is AMD's recommendation for the Zynq HP ports) |

Out-of-space values fail at elaboration with `$error` (tested: `DATA_W=16`, `DATA_W=256`, `ADDR_W=31`, `ADDR_W=65`, `MAX_BURST=0`, `MAX_BURST=257`, `OUTSTANDING=0`, `OUTSTANDING=17`, `DIR=2`).

## Interfaces

- `s_axi`: axi4-lite (dir slave). control registers; 6-bit address, 32-bit data
- `m_axi`: axi4 (dir master). AR, R, AW, W, B; INCR only, AxSIZE = log2(DATA_W/8) (the one-beat status write is 4 bytes), no IDs, AxCACHE = AXCACHE, no lock, prot or qos
- `s_axis`: axi4-stream (dir slave). used when DIR = 1; tdata only (tlast ignored); tready low and idle when DIR = 0
- `m_axis`: axi4-stream (dir master). used when DIR = 0; tdata and tlast (on the last beat of each descriptor's buffer); idle when DIR = 1

Clocks: `aclk`. Reset: `aresetn`, active low, synchronous.

## Registers

This block differs from the house register conventions (docs/hwsw.md) in 3 ways: unmapped addresses inside the block: OKAY and read 0 (house: a read answers SLVERR with data 0 and a write answers OKAY and changes nothing); it records no unmapped accesses (house: the ERR_ADDR and ERR_STATUS error-capture registers); byte strobes are ignored, so every write changes the whole word (house: strobes honoured). Generated from `register_map` in `ip.yaml` by `hwsw/regmap.py`; the 0x40-byte window decodes address bits [5:2]. Unmapped addresses: OKAY and read 0.

### Register map

| Offset | Register | Reset | Summary |
|---|---|---|---|
| 0x000 | CTRL | 0x00000000 | Run and interrupt enable. Clear RUN only when STATUS.IDLE is 1 (the engine does not stop in the middle of a descriptor). |
| 0x004 | STATUS | 0x00000001 | Engine state and sticky bits. |
| 0x008 | RING_LO | 0x00000000 | Ring base address, bits 31 to 4. Bits 3 to 0 read 0 (the ring is 16-byte aligned). Write only while the engine is idle. |
| 0x00c | RING_HI | 0x00000000 | Ring base address, bits 63 to 32 (bits above ADDR_W are ignored). Write only while the engine is idle. |
| 0x010 | RING_SIZE | 0x00000000 | Entries in the ring, 1 to 65535. 0 keeps the engine idle. Write only while the engine is idle. |
| 0x014 | HEAD | 0x00000000 | Producer index. Software writes it after filling descriptors; it must stay below RING_SIZE. The engine owns the entries from TAIL up to, not including, HEAD. |
| 0x018 | TAIL | 0x00000000 | Consumer index, the next entry the engine takes. Software reads it to find free slots; it moves after an entry's status word is in memory. |
| 0x01c | IRQ_THRESH | 0x00000000 | Completions per interrupt; 0 acts as 1. The interrupt also fires when the ring drains (TAIL reaches HEAD), and at once for a descriptor with IOC set. |
| 0x020 | DONE_COUNT | 0x00000000 | Descriptors completed since reset, wrapping at 2^32. |
| 0x024 | ERR | 0x00000000 | Error record. Bits 3 and 1:0 describe the latest data error; bit 2 means a descriptor fetch or a status write failed. |

Reset is what a read returns after reset with every hardware input low.

### Access types

| Access | Meaning |
|---|---|
| RW | read/write: software writes the value; hardware sees it on an output |
| RO | read-only: the value comes from a hardware input (or is a constant); writes are ignored |
| W1C | write 1 to clear: hardware sets bits with a pulse input; software clears a bit by writing 1 to it; a set and a clear in the same clock leave the bit set (no event is lost) |

### Behaviour

- **Unmapped addresses.** An address inside this block's 0x40-byte window that holds no register answers OKAY and reads 0; a write there is ignored. Addresses outside the window belong to the interconnect (an AXI crossbar answers DECERR there).
- **Error capture.** None: this block records nothing about accesses to unmapped addresses.
- **Reserved bits.** Bits that belong to no field read 0 and ignore writes. Write them as 0, so that a later version can give them a meaning.
- **Reads have no side effects.** Reading any register changes nothing, so a debugger or a retried read is safe. A read-modify-write must write the W1C, W1S and W1P bits as 0 (here STATUS.HALTED, STATUS.IRQ, ERR.CODE, ERR.HALT_CAUSE, ERR.DATA_ERR), or it clears, sets or pulses them: write back only the RW bits of what was read. This block has no command, doorbell or snapshot bits. A write to a read-only register is answered OKAY and ignored.
- **Same-clock priority (the house convention).** W1C bits (STATUS.HALTED, STATUS.IRQ, ERR.CODE, ERR.HALT_CAUSE, ERR.DATA_ERR): a hardware set in the same clock as a software clear wins, so the bit stays set and no event is lost.
- **Partial writes.** Byte strobes (WSTRB) are ignored on every register: every write changes the whole 32-bit word, so a CPU's byte or halfword store overwrites the other bytes. Use 32-bit stores only.
- **Access width and alignment.** 32-bit registers on a 32-bit AXI4-Lite bus. AXI4-Lite has no transfer size: a CPU's byte or halfword load reads the whole word, and its store arrives as a word write with fewer strobes (see Partial writes). Address bits [1:0] are not decoded, so an unaligned address reaches the word that holds it; only bits [5:2] are decoded, so the window repeats every 0x40 bytes. Use aligned 32-bit accesses.
- **Values wider than 32 bits.** No snapshot groups: every register is read on its own, so a value split across two registers (a HI and a LO) can tear if it changes between the two reads. Give such a value a snapshot group.
- **Reset.** `aresetn`, synchronous, active low (sampled on the rising edge of `aclk`). Every stored field takes the reset value in its table. Every register is reset.
- **Interrupt.** None: this block has no interrupt output; software polls its status.
- **Clock domain and timing.** Every field is in the `aclk` domain; hardware inputs must be synchronous to `aclk` (the block has no synchronisers). A write takes effect on the hardware in the clock its write response (BVALID) is raised. A read returns the hardware's values as they were in the clock the read address was accepted.

### CTRL (0x000)

Run and interrupt enable. Clear RUN only when STATUS.IDLE is 1 (the engine does not stop in the middle of a descriptor).

| Bits | Field | Access | Reset | Summary |
|---|---|---|---|---|
| 1 | IRQ_EN | RW | 0x0 | the irq pin follows STATUS.IRQ |
| 0 | RUN | RW | 0x0 | the engine takes descriptors while HEAD differs from TAIL |

### STATUS (0x004)

Engine state and sticky bits.

| Bits | Field | Access | Reset | Summary |
|---|---|---|---|---|
| 2 | IRQ | W1C | 0x0 | an interrupt is pending; clearing it also restarts the coalescing count |
| 1 | HALTED | W1C | 0x0 | a descriptor fetch or a status write failed; the engine stops with TAIL unchanged until this is cleared |
| 0 | IDLE | RO | 0x1 | no descriptor is being worked on |

### RING_LO (0x008)

Ring base address, bits 31 to 4. Bits 3 to 0 read 0 (the ring is 16-byte aligned). Write only while the engine is idle.

| Bits | Field | Access | Reset | Summary |
|---|---|---|---|---|
| 31:4 | BASE | RW | 0x0 |  |

### RING_HI (0x00c)

Ring base address, bits 63 to 32 (bits above ADDR_W are ignored). Write only while the engine is idle.

| Bits | Field | Access | Reset | Summary |
|---|---|---|---|---|
| 31:0 | BASE | RW | 0x0 |  |

### RING_SIZE (0x010)

Entries in the ring, 1 to 65535. 0 keeps the engine idle. Write only while the engine is idle.

| Bits | Field | Access | Reset | Summary |
|---|---|---|---|---|
| 15:0 | ENTRIES | RW | 0x0 |  |

### HEAD (0x014)

Producer index. Software writes it after filling descriptors; it must stay below RING_SIZE. The engine owns the entries from TAIL up to, not including, HEAD.

| Bits | Field | Access | Reset | Summary |
|---|---|---|---|---|
| 15:0 | INDEX | RW | 0x0 |  |

### TAIL (0x018)

Consumer index, the next entry the engine takes. Software reads it to find free slots; it moves after an entry's status word is in memory.

| Bits | Field | Access | Reset | Summary |
|---|---|---|---|---|
| 15:0 | INDEX | RO | 0x0 |  |

### IRQ_THRESH (0x01c)

Completions per interrupt; 0 acts as 1. The interrupt also fires when the ring drains (TAIL reaches HEAD), and at once for a descriptor with IOC set.

| Bits | Field | Access | Reset | Summary |
|---|---|---|---|---|
| 15:0 | COUNT | RW | 0x0 |  |

### DONE_COUNT (0x020)

Descriptors completed since reset, wrapping at 2^32.

| Bits | Field | Access | Reset | Summary |
|---|---|---|---|---|
| 31:0 | COUNT | RO | 0x0 |  |

### ERR (0x024)

Error record. Bits 3 and 1:0 describe the latest data error; bit 2 means a descriptor fetch or a status write failed.

| Bits | Field | Access | Reset | Summary |
|---|---|---|---|---|
| 3 | DATA_ERR | W1C | 0x0 | some data beat answered SLVERR or DECERR |
| 2 | HALT_CAUSE | W1C | 0x0 | a descriptor fetch or status write failed |
| 1:0 | CODE | W1C | 0x0 | the latest non-OKAY data response: 2 SLVERR or 3 DECERR |


## Latency and throughput

- descriptor start: from a HEAD write to the first descriptor fetch address a few clocks; a descriptor costs a fetch round trip, the data, and a status write round trip, one after the other (no prefetch); the measured figures are in DATASHEET.md
- data: one beat a clock in steady state when the memory and the stream keep up; the first beat after the descriptor fetch needs one address round trip
- throughput: one memory beat per clock at the port limit once the bursts are in flight (DATA_W/8 bytes a clock); the descriptor and status round trips are paid once per descriptor, so small descriptors are slower (measured in DATASHEET.md)

## Evidence

cocotb bench with a memory model (read and write latency, random ready and valid gaps, SLVERR and DECERR, an AXI rule monitor) at ten points; formal AXI rule proofs (SymbiYosys with slang); 22 seeded faults. Tests: `ip_lib/sg_dma/tb/test_sg_dma_rtl.py`, `ip_lib/sg_dma/tb/test_sg_dma_formal.py`.

Try it: `python3 -m pytest ip_lib/sg_dma/tb/test_sg_dma_rtl.py ip_lib/sg_dma/tb/test_sg_dma_formal.py` (the formal jobs need SymbiYosys on PATH; they are skipped without it).

Parameter points simulated: `DIR=0, DATA_W=32, MAX_BURST=16, OUTSTANDING=4`; `DIR=1, DATA_W=32, MAX_BURST=16, OUTSTANDING=4`; `DIR=0, DATA_W=64, MAX_BURST=8, OUTSTANDING=2`; `DIR=1, DATA_W=64, MAX_BURST=8, OUTSTANDING=2`; `DIR=0, DATA_W=128, MAX_BURST=4, OUTSTANDING=1, ADDR_W=40`; `DIR=1, DATA_W=128, MAX_BURST=4, OUTSTANDING=8, ADDR_W=40`; `DIR=0, MAX_BURST=1, OUTSTANDING=1`; `DIR=1, MAX_BURST=256, OUTSTANDING=16`; `DIR=0, DATA_W=64, MAX_BURST=256, OUTSTANDING=3`; `DIR=1, DATA_W=64, MAX_BURST=3, OUTSTANDING=4`.

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `no_4k_split` | a burst is not cut at the 4 KB boundary | caught |
| `arlen_off_by_one` | the read burst length field is not beats minus one | caught |
| `tlast_every_burst` | tlast on the last beat of every burst, not of every descriptor | caught |
| `wlast_early` | wlast one beat early | caught |
| `status_address` | the status word is written over the length word | caught |
| `ring_wrap` | the ring has one entry too many before it wraps | caught |
| `slverr_read_ignored` | SLVERR on a read beat is not reported, only DECERR | caught |
| `slverr_write_ignored` | SLVERR on a write response is not reported, only DECERR | caught |
| `rready_ignores_sink` | read data is accepted whether or not the stream sink is ready, so a beat is lost under back pressure | caught |
| `outstanding_one_over` | one more burst in flight than OUTSTANDING allows | caught |
| `irq_threshold_off_by_one` | the interrupt fires one completion late | caught |
| `ioc_ignored` | the interrupt-on-completion flag of a descriptor does nothing | caught |
| `bad_reports_bytes` | a descriptor that moved nothing reports its length as moved | caught |
| `misaligned_address_accepted` | a buffer address that is not beat aligned is accepted and issued | caught |
| `status_fail_not_halting` | a failed status write does not halt the engine | caught |
| `desc_fetch_not_drained` | a failed descriptor fetch stops reading after the first bad beat, leaving the rest of the burst in the memory's read channel | caught |
| `w_before_aw` | stream data is written before any burst address has been issued | caught |
| `status_w_before_aw` | the status data is offered before its address has been accepted | caught |
| `tail_not_advanced` | the consumer index never moves | caught |
| `done_count_double` | the completion counter counts two | caught |
| `strobe_lane` | the status write's byte strobes ignore which 32-bit lane of a wide beat holds the word | caught |
| `ring_base_unaligned` | a ring base that is not 16-byte aligned is taken as it is, so a descriptor fetch can cross a 4 KB boundary | caught |

## Cost (out of context)

Built alone (out of context) on an Artix-7, xck26-sfvc784-2LV-c, for a 4.0 ns clock (250 MHz), Vivado 2026.1 (build 6511674); source: [char/xck26-sfvc784-2LV-c.json](char/xck26-sfvc784-2LV-c.json). Not run on a board.

| ADDR_W | DATA_W | MAX_BURST | OUTSTANDING | DIR | AXCACHE | LUT | FF | LUT RAM | Block RAM tiles | DSP | WNS (ns) | Fmax estimate (MHz) | Dynamic power (W) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 32 | 32 | 16 | 4 | 0 | 3 | 571 | 501 | 0 | 0 | 0 | 0.492 | 285.1 | 0.006 |
| 32 | 32 | 16 | 4 | 1 | 3 | 566 | 504 | 0 | 0 | 0 | 0.504 | 286.0 | 0.007 |
| 32 | 64 | 16 | 4 | 0 | 3 | 601 | 450 | 0 | 0 | 0 | 0.602 | 294.3 | 0.006 |
| 32 | 64 | 16 | 4 | 1 | 3 | 578 | 452 | 0 | 0 | 0 | 0.661 | 299.5 | 0.007 |
| 32 | 128 | 16 | 4 | 0 | 3 | 588 | 439 | 0 | 0 | 0 | 0.638 | 297.4 | 0.006 |
| 32 | 128 | 16 | 4 | 1 | 3 | 583 | 442 | 0 | 0 | 0 | 0.696 | 302.7 | 0.007 |

Defaults: ADDR_W 32, DATA_W 32, MAX_BURST 16, OUTSTANDING 4, DIR 0, AXCACHE 3. WNS is the worst negative slack (the timing margin at the target clock; below zero the target is missed).

Fmax is estimated from one routed run at the target clock (1000 / (period - WNS)); dynamic power is vectorless (default toggle rates). Regenerate with `python3 -m flow.ipchar sg_dma` (Vivado, minutes per point).

## Boundary and reuse

- Registered outputs: the AXI4-Lite response channels and all engine state are flops; the AXI4 address and data channels are combinational from state (AR, AW, wlast, tlast) or pass the memory's and the stream's own handshakes through (rready follows m_axis_tready, s_axis_tready follows m_axi_wready).
- Clock crossings: none (one clock).
- Part, board or pin: none.
- Depends on: nothing.

## Cost table

results/241_dma/ooc.json and char/ (out-of-context Vivado 2026.1 on xck26 and xc7z020, both directions at DATA_W 32, 64 and 128: about 570 to 640 LUTs, 440 to 500 flip-flops, no block RAM or DSP).

Licence: MIT (this repository).

## Known gaps and limits

- One descriptor at a time (no descriptor prefetch); one direction per instance; no data realignment (buffer address and length are whole beats); no IDs; S2MM takes exactly the descriptor's length from the stream and ignores tlast; the stream-to-memory path passes s_axis and m_axi handshakes through combinationally.
- Board: no board run of this entry is recorded; its evidence is simulation and out-of-context builds.
- No descriptor prefetch: a descriptor costs a full fetch and status round trip, so descriptors below about a thousand bytes lose most of the port bandwidth (measured in DATASHEET.md).
- Timing: the burst-length function sits in the path to the data-side counters, 14 logic levels, so the engine runs near 100 MHz on a Zynq-7000 (-1) and meets 4 ns on the K26 with margin; registering the burst length would shorten it (results/241_dma/README.md).
- No board run: the KR260 throughput and latency measurement is pre-registered (docs/241_dma_prereg.md) and has not been run.
- The memory model is ours; no run against AMD interconnect or a PS port has been made, so back pressure and latency of the real Zynq HP and HPC ports are not covered.
- S2MM does not end a descriptor on tlast, so a packet shorter than its buffer needs the software to know the length; a packet-oriented S2MM engine is a follow-up.

## Next steps

1. Register the burst length once per burst to shorten the critical path, then re-run the proofs and the seeded faults.
2. Run the pre-registered KR260 measurement through the owner (docs/241_dma_prereg.md).
3. Add descriptor prefetch and compare the small-descriptor throughput with the measured baseline.
4. Add a tlast-terminated S2MM mode and a status word that reports the bytes received.

## History

- 0.1.0 (2026-11-26): First version (brief 241). See README.md and DATASHEET.md.

Full entries: [CHANGELOG.md](CHANGELOG.md).
