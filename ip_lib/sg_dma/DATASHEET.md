# sg_dma datasheet (version 0.1.0, brief 241)

A scatter-gather DMA engine between one AXI4 memory-mapped master and one AXI4-Stream port, driven by a ring of 16-byte descriptors in memory and an
AXI4-Lite control port. `DIR` = 0 moves memory to the stream (MM2S), `DIR` = 1 the stream to memory (S2MM); one direction per instance. Every figure below is
measured in simulation (`results/241_dma/summary.json`, 2026-11-26, Icarus Verilog 14, a memory model of ours) or proved (`results/241_dma/formal.json`);
the Vivado figures are in `results/241_dma/ooc.json`; **nothing here is a board measurement** (the board run is pre-registered in `docs/241_dma_prereg.md`).

## When to use it, and when not to

Use it for a stream that moves blocks to or from memory with a ring of buffers software publishes and reclaims, where one engine per direction is enough.
Use AMD's AXI DMA (PG021) when you need its driver, data realignment, a tlast-terminated receive with a received-byte count, or several channels; use AXI VDMA for
video frames. The KB skill `dma-engine-selection` compares them. This engine is smaller and starts a transfer sooner than a vendor core in scatter-gather mode
(measured start-up below, with the caveat in "Against AMD's AXI DMA"), and has no descriptor prefetch, which costs small transfers dearly (table below).

## Descriptor ring and driver contract

The ring is `RING_SIZE` descriptors of 16 bytes at `RING_BASE` (16-byte aligned: bits 3:0 of `RING_LO` read 0). One descriptor, four little-endian 32-bit words:

| Word | Bits | Meaning |
|---|---|---|
| 0 | 31:0 | buffer address, bits 31:0 |
| 1 | 31:0 | buffer address, bits 63:32 (bits above `ADDR_W` are ignored) |
| 2 | 23:0 | length in bytes |
| 2 | 31 | IOC: raise the interrupt when this descriptor completes, ahead of the coalescing count |
| 3 | 31 | DONE, written by the engine |
| 3 | 30 | ERR: a data beat answered SLVERR or DECERR |
| 3 | 29 | BAD: the descriptor was misaligned or empty and nothing moved |
| 3 | 25:24 | the first non-OKAY response code (2 SLVERR, 3 DECERR) |
| 3 | 23:0 | bytes moved (0 when BAD) |

Software: write words 0 to 2 (word 3 is cleared), then write `HEAD` (the producer index; it must stay below `RING_SIZE`). The engine owns the entries from `TAIL` up to
but not including `HEAD` and software must not touch them. A descriptor is finished when its word 3 shows DONE; the entry is free once `TAIL` has passed it. Free slots are
`RING_SIZE - 1 - ((HEAD - TAIL) mod RING_SIZE)`: **always derive them from `TAIL`**, not from the status words (the engine writes the status word before it advances `TAIL`, so a
slot freed by status alone can be refilled while `TAIL` still points at it, and a `HEAD` that catches `TAIL` looks like an empty ring). The ring holds at most `RING_SIZE - 1` entries.
A buffer's address and length must be multiples of `DATA_W/8` bytes and the length at least one beat, else the descriptor completes with BAD and moves nothing. The ring, its registers and the
buffers are in memory the master can reach; on a Zynq PS port software must clean and invalidate caches around transfers (KB skill `dma-coherency-and-driver-contract`; the status word must not share a cache line with a word software writes).

MM2S sends the buffer's beats on `m_axis` with `tlast` on the last beat of each descriptor's buffer. S2MM takes exactly the descriptor's length from `s_axis` (its `tlast` is
ignored: a packet shorter than its buffer is not detected) and reports the buffer length, not a received length, in word 3.

## Behaviours a user could guess wrong (all tested or proved unless marked)

- **Bursts.** INCR only, `AxSIZE` = log2(`DATA_W/8`) (the one-beat status write is 4 bytes with the matching byte strobes), at most `MAX_BURST` beats, never across a 4 KB boundary (proved); the
  next burst starts where the last ended. A descriptor fetch is one burst of 16 bytes. No IDs (one ID, responses in order), no `AxLOCK`, `AxPROT` 0, `AxQOS` 0; `AxCACHE` is the parameter `AXCACHE`.
- **Outstanding.** At most `OUTSTANDING` data bursts are in flight (proved to depth 30); write data is offered only after its address was accepted, the status data too (proved to depth 30).
  The engine accepts read data only for an address it issued and a write response only for a burst whose data has all gone.
- **Order of work.** One descriptor at a time: fetch, data, status write, then the next fetch. There is no prefetch and no overlap between descriptors.
- **Errors.** SLVERR or DECERR on a data beat sets ERR and the code in the descriptor, `ERR.DATA_ERR` and `ERR.CODE`, and the engine finishes the descriptor and goes on (an MM2S beat with an error
  response is still sent on the stream). A failed descriptor fetch (any non-OKAY beat) or a failed status write sets `STATUS.HALTED` and `ERR.HALT_CAUSE`, leaves `TAIL` where it is and stops; the rest of the
  failed fetch burst is read and discarded first so the memory's read channel stays in step. Writing 1 to `STATUS.HALTED` restarts the engine at the same entry.
- **Registers.** 32-bit words, `addr[5:2]` selects, byte strobes ignored, every access answers OKAY: a hole reads 0 and ignores writes; a write to a read-only register is ignored. Write and address arrive together
  (the engine accepts both in one clock, one access at a time). Same-clock priorities: a hardware set of `STATUS.IRQ`, `HALTED` or an `ERR` bit wins over a software clear in the same clock. `RING_*` and `RING_SIZE` are used
  live: write them only while `STATUS.IDLE` is 1 and `RUN` is 0 (the descriptor address is latched when an entry is taken, so a change mid-entry does not corrupt it, but the next entry uses the new ring).
- **Interrupt.** `irq` is high while `STATUS.IRQ` and `CTRL.IRQ_EN` are both 1. `STATUS.IRQ` is set when a descriptor completes and `IOC` is set, or the completions since the last interrupt reach `IRQ_THRESH` (0 acts as 1), or the ring has drained
  (`TAIL` equals `HEAD`): without the last rule a count of N would strand the last N-1 completions. Writing 1 to `STATUS.IRQ` clears it and restarts the count. Completions are counted only when the status write was answered OKAY.
- **Reset.** `aresetn`, active low, synchronous; every register is 0 afterwards (`STATUS.IDLE` reads 1). The stream and memory handshakes are low in reset. A reset in the middle of a burst leaves the memory with an address or data
  it never completes: reset the memory side too.
- **Clock.** One clock `aclk`; no crossing.
- **Not covered:** unaligned buffers (they complete as BAD), several descriptors in flight, data realignment, IDs, write data interleaving, exclusive access, narrow bursts other than the status write. A buffer that crosses a 4 KB page is covered: it is cut into bursts at the boundary.

## Verification

Cocotb against `model.py` (descriptor format, the burst split, the status word) with a memory model that has read and write latency, random ready and valid gaps, response errors and an AXI rule monitor; ten
(`DIR`, `DATA_W`, `MAX_BURST`, `OUTSTANDING`, `ADDR_W`) points; SymbiYosys with the slang front end; 22 seeded faults (`faults.yaml`). The AXI hold rules (AR, AW, W, the stream port, the AXI4-Lite B and R), burst size,
alignment and the 4 KB rule are proved by k-induction at 32, 64 and 128 bits in both directions with a free memory, free AXI4-Lite master and free stream (the descriptor words read are arbitrary, so the proof covers every
buffer address and length); write data after address, `wlast` and the outstanding limit are proved to depth 30 only, because their bookkeeping is in the harness and not tied to the engine's own counters. There is no formal rigour sidecar yet.

## Measured behaviour (simulation, not a board)

Memory model: read latency 20 clocks, write response latency 15, no random gaps, always-ready stream. Fraction of the port limit (`DATA_W/8` bytes a clock) over six descriptors of the same size back to back,
`HEAD` write to last status response, descriptors included:

<!-- measured:begin -->
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
<!-- measured:end -->

The first table is the fraction of the port limit; the second is the clocks from the `HEAD` write to the status response for **one** descriptor; the third is the like-for-like point against AMD's published
figures. A descriptor costs about 64 clocks beyond its data in this memory (a descriptor fetch round trip, the first data round trip and the status write round trip, one after the other, with this memory's latencies): that is why 64 bytes reaches 0.2 of the port and 16 KB 0.985.
Fewer bursts in flight cost more than short bursts: one burst in flight with 16-beat bursts and 20 clocks of read latency settles at 0.44 (about 16/(16+20)).
Plots: `results/241_dma/throughput_vs_size.svg`, `results/241_dma/latency_overhead.svg`.

## Against AMD's AXI DMA (PG021 v7.1)

`amd_axi_dma_model.py` is a behavioural model of the documented behaviour only (validity envelope and what is documented versus inferred are at the top of the file and in `results/241_dma/README.md`): PG021 table 1 gives 10 + 28 + 6 clocks from a tail-descriptor write
to the first MM2S stream beat and 39 clocks from the first S2MM stream beat to the first write address; table 2 gives 399.04 MB/s (MM2S) and 298.59 MB/s (S2MM) for 10,000 bytes at 100 MHz, 32-bit. Our engine at 10,000 bytes in a memory of our own (third table above)
sustains the port limit in both directions; **the comparison is not equal-conditions**: AMD's test bench memory, its latency and its stream are not stated, so its S2MM gap of 5 to 6 clocks a burst (our inference, 298.59 MB/s)
may come from the memory side and not the core. The AXI DMA was not run (no simulation or board run of the vendor core in this brief); the figures are the document's.

## Cost

Out-of-context Vivado 2026.1 on `xck26-sfvc784-2LV-c` (KR260) and `xc7z020clg484-1`: `results/241_dma/ooc.json` (see the README for the table).
