# Results: AMD AXI4-Lite IP register and bus-response conventions, measured in simulation

Brief 69 measured how nine AMD IP blocks behave at their AXI4-Lite register port, in the Vivado 2026.1 simulator, and
compared each result with the product guide held locally and with our own house register conventions (`docs/hwsw.md`,
"House conventions"). Seven blocks are peripherals (AXI GPIO, UART Lite, Timer, Interrupt Controller, IIC, Quad SPI and the
DMA register port) and two are interconnects (SmartConnect and the AXI Interconnect). The probes drive the IP through our
AXI transactor with our protocol checker watching every wire; the benches and how to run them are in
[amd_ip_probe](../../amd_ip_probe/README.md). The agent's note that uses the table is `flow/amd_ip_notes.py`; the knowledge
bank skill is `amd-axi4-lite-ip-register-behaviour` in the AMBA/AXI unit.

Everything here is behavioural simulation of the IP as delivered: no implementation, no board. Where a source file in the
Vivado install was read to explain a result, the explanation is given in our own words and the measurement is the evidence.

## Summary

Legend: `=` the same as the house convention, `≠` differs (how), `n/a` not applicable, `?` not probed (why). "Estimate"
marks a result that depends on locating the coincident clock from interrupt-output delays (see the gaps below).

<!-- summary:begin -->
| Point | House convention | AXI GPIO 2.0 | AXI UART Lite 2.0 | AXI Timer 2.0 | AXI Interrupt Controller 4.1 | AXI IIC 2.1 | AXI Quad SPI 3.2 | AXI DMA 7.1 (register port) | SmartConnect 1.0 | AXI Interconnect 2.1 |
|---|---|---|---|---|---|---|---|---|---|---|
| Read of a hole inside the IP's window | SLVERR, data 0 (`unmapped: split`) | ≠ OKAY, data 0 (112 of 128 words) | n/a no hole: four registers fill the 16-byte window | ≠ OKAY, 0 (words 0x0C and 0x1C) | ≠ OKAY, 0 (126 of 128 words are 0 at reset; IVAR and IMR read 0 in basic mode) | ≠ OKAY, 0 (every word of the window answers OKAY) | ≠ OKAY, 0; SLVERR only for the empty receive FIFO (0x6C) | ≠ OKAY, 0 (every word of the 1 KB window answers OKAY) | n/a a slave's hole is the slave's answer (OKAY, 0) | n/a a slave's hole is the slave's answer (OKAY, 0) |
| Write to a hole | OKAY, ignored (and recorded by the error capture) | = OKAY, ignored (apart from the aliases) | = OKAY, ignored (writes to the read-only FIFO and status words) | = OKAY, ignored (words 0x0C and 0x1C) | = OKAY, ignored | = OKAY, ignored; SLVERR only for 0xFFFFFFFF written to the soft-reset word (0x40; the documented value was not tried) | = OKAY, ignored; SLVERR only for 0xFFFFFFFF written to the soft-reset word (0x40; the documented value was not tried) | = OKAY, ignored | n/a a slave's own answer | n/a a slave's own answer |
| Address aliasing (partial decode) | none: a hole is a hole; address bits [1:0] are not decoded | ≠ yes: in 0x100-0x1FF address bits [7:6] are ignored, so GIER, ISR and IER repeat at +0x40, +0x80, +0xC0 | n/a no hole to alias; the byte offsets alias the word (see address bits [1:0]) | = none in the 32-byte window | = none in the 512-byte window | ≠ yes: a write at 0x180-0x1FF acts on 0x100-0x17F (address bit 7 ignored above 0x100) | = none in the 128-byte window | ≠ yes: the 128-byte register block repeats eight times in the 1 KB window (address bits [9:7] ignored) | = the address reaches the slave unmodified: the slave's own alias appears through it | = the address reaches the slave unmodified: the slave's own alias appears through it |
| Reserved bits | read 0, writes ignored | = read 0; writes ignored (GIER bit 31 only, IER 2 bits, TRI to the channel width) | = write-only CTRL: only the interrupt enable bit shows in STAT | = TCSR0 bits 31:12 never read back set when written | = IER 4 bits, MER 2 bits, the rest read 0 | = the interrupt enable word stores 8 bits | = the interrupt enable word stores 9 bits | ? write-all-ones read-back is in the record; reserved bits of the control words were not probed bit by bit | n/a | n/a |
| Read side effects | none; a pop or an acknowledge is a W1P write | = none: ISR and data reads repeat | ≠ the RX FIFO read pops it; a STAT read clears the overrun and frame error bits (parity not exercised: the bench has none) | ? not isolated: the auto-reload bench re-sets T0INT every 64 clocks, so a surviving flag does not prove a read leaves it alone | = none seen: IVR reads the same twice | ? no word read differently twice at reset, but the receive FIFO pop needs a transfer | ? no word read differently twice at reset, but the receive FIFO pop needs a transfer | ? no word read differently twice at reset (weak: a status or FIFO effect needs a transfer) | n/a | n/a |
| How a status bit is cleared | write 1 to clear (W1C), or a W1P command | ≠ toggle on write: writing 1 flips the ISR bit, so 1 to a clear bit sets it | ≠ clear on read of STAT (error bits); FIFO resets are write-only CTRL bits | = W1C: write 1 clears T0INT, write 0 changes nothing | ≠ a separate write-1-to-acknowledge register (IAR); a level input stays latched after it drops, until acknowledged | ? needs a transfer or an error to set a status bit | ? needs a transfer or an error to set a status bit | ? needs a transfer or an error to set a status bit | n/a | n/a |
| Hardware set against a software clear in the same clock | the hardware set wins; the event is not lost | = the event is kept: the estimate of the coincident clock (-9, from two measured delays) equals the first clock giving 1; exact to +-1 clock | ? a received character cannot be timed against a status read from outside | ≠ consistent with the clear winning (event lost) at the coincident clock, if the estimate is exact to +-1 clock; the source shows a flag flop whose reset beats its set | ≠ the acknowledge wins at the estimated coincident clock (-3) and the next one (-2); edges sampled at -1 or later are kept (the source shows a registered acknowledge pulse with priority over the set); estimate, exact to +-1 clock | ? needs a transfer to create the hardware event | ? needs a transfer to create the hardware event | ? needs a transfer to create the hardware event | n/a | n/a |
| Byte strobes (WSTRB) | honoured bit by bit | ≠ ignored (a write with strobe 0000 takes effect) | ≠ ignored (a write with strobe 0000 transmits) | ≠ ignored | ≠ ignored | ≠ ignored | ≠ ignored | ≠ the lite port has no WSTRB input | ? not observable: both slaves ignore WSTRB | ? not observable: both slaves ignore WSTRB |
| Address bits [1:0] of a word access | not decoded: any byte address in the word reaches it | = bits [1:0] ignored, writes and reads | = bits [1:0] ignored (a read at byte 1 of the RX FIFO word pops it) | = bits [1:0] ignored | = bits [1:0] ignored | = bits [1:0] ignored | = bits [1:0] ignored | ≠ writes ignore bits [1:0]; a read at +1, +2 or +3 returns 0 | = bits [1:0] reach the slave, which ignores them | = bits [1:0] reach the slave, which ignores them |
| Second address before the first response | one transaction outstanding per direction | = one address (and one data word) accepted before the first response, then it waits (a second write not shown to land for IIC, Quad SPI and the interconnects) | = one address (and one data word) accepted before the first response, then it waits (a second write not shown to land for IIC, Quad SPI and the interconnects) | = one address (and one data word) accepted before the first response, then it waits (a second write not shown to land for IIC, Quad SPI and the interconnects) | = one address (and one data word) accepted before the first response, then it waits (a second write not shown to land for IIC, Quad SPI and the interconnects) | = one address (and one data word) accepted before the first response, then it waits (a second write not shown to land for IIC, Quad SPI and the interconnects) | = one address (and one data word) accepted before the first response, then it waits (a second write not shown to land for IIC, Quad SPI and the interconnects) | ≠ reads: one. Writes: a second AW and W are accepted while the first B waits, and only one B comes back for the two writes | = one address (and one data word) accepted before the first response, then it waits (a second write not shown to land for IIC, Quad SPI and the interconnects) | = one address (and one data word) accepted before the first response, then it waits (a second write not shown to land for IIC, Quad SPI and the interconnects) |
| AW without W, W without AW | each channel accepted independently, in either order | ≠ waits for both: AW alone or W alone is not accepted in 20 clocks | ≠ waits for both: AW alone or W alone is not accepted in 20 clocks | ≠ waits for both: AW alone or W alone is not accepted in 20 clocks | ≠ waits for both: AW alone or W alone is not accepted in 20 clocks | ≠ waits for both: AW alone or W alone is not accepted in 20 clocks | ≠ waits for both: AW alone or W alone is not accepted in 20 clocks | ≠ waits for both: AW alone or W alone is not accepted in 20 clocks | ≠ waits for both: AW alone or W alone is not accepted in 20 clocks | ≠ accepts AW alone; W alone is not accepted until AW is present |
| Values wider than 32 bits | snapshot group: a W1P trigger copies the whole value | n/a | n/a | ≠ no snapshot: the 64-bit cascade reads as TCR0 and TCR1 separately and a read across the carry tears (4 of 12 low-first trials and 7 of 12 high-first trials showed an out-of-order value) | n/a | n/a | n/a | n/a | n/a | n/a |
| Reset | `aresetn`, synchronous, every register to its reset value | = IER, GIER, TRI1, DATA1 back to reset (TRI2, DATA2 never written) | = both FIFOs empty (STAT back to its reset value) | = TCSR and TLR back to 0 (no counter running) | = IER and MER back to reset after writes (IVR and ILR read all ones; ISR and IVAR not exercised) | ? each write in the scan was followed by a reset; the baseline words came back, not checked word by word | ? each write in the scan was followed by a reset; the baseline words came back, not checked word by word | ? each write in the scan was followed by a reset; the baseline words came back, not checked word by word | = the slave behind it resets with it | = the slave behind it resets with it |
| Interrupt output | level, from a register, one clock after the cause | = level, from registers; cleared through ISR; 9 clocks from an input edge (information, not one clock) | ≠ two one-clock pulses per character, not a level (the guide says RX non-empty and TX empty; which pulse is which was not timed) | = level, from a flag register (the guide agrees) | = level, from the latched ISR, IER and MER; nothing out while MER is 0 (ISR was also 0 then) | ? needs a transfer or an error to raise it | ? needs a transfer or an error to raise it | ? needs a transfer or an error to raise it | n/a | n/a |
| Latency, minimum, no back-pressure (AXI clocks) | not a convention: for planning | n/a write 7, read 7 | n/a write 5, read 5 | n/a write 5, read 5 | n/a write 6, read 6 | n/a write 6, read 6 | n/a write 7, read 7 | n/a write 7, read 6 | n/a write 10, read 10 | n/a write 9, read 10 |
| Address outside every slave (interconnects) | DECERR from the interconnect (`axil_xbar`) | n/a | n/a | n/a | n/a | n/a | n/a | n/a | = DECERR for read and write at 0x0, 0xFFC, 0x3000, 0x8000, 0x80000000 and 0xFFFFFFFC; read data 0xDEC0DEE3; the write data is consumed | = DECERR for read and write at the same addresses; read data 0xDEC0DE1C; the write data is consumed |
| A slave's SLVERR through the interconnect | passed to the master unchanged | n/a | n/a | n/a | n/a | n/a | n/a | n/a | = the UART Lite's SLVERR for an empty receive FIFO reaches the master as SLVERR | = the UART Lite's SLVERR for an empty receive FIFO reaches the master as SLVERR |
| Responses across two slaves, one unmapped (interconnects) | in the order of the requests | n/a | n/a | n/a | n/a | n/a | n/a | n/a | = responses DECERR then OKAY; the interconnect took one request at a time, so ordering was not exercised | = responses DECERR then OKAY; the interconnect took one request at a time, so ordering was not exercised |
<!-- summary:end -->

The table is written from [amd_ip_probe/summary_spec.py](../../amd_ip_probe/summary_spec.py) and every cell names the probe
lines that show it; `python3 amd_ip_probe/summarise.py --check` (and CI, through `amd_ip_probe/tests/test_records.py`)
fails when a cell says something its record does not.

## What differs from our house conventions, and what bites

- **Holes answer OKAY with 0, not SLVERR.** Every peripheral does this (GPIO, Timer, INTC, IIC, Quad SPI, DMA). The one
  SLVERR a peripheral gives is for a state, not an address: the UART Lite's empty receive FIFO and full transmit FIFO, the
  Quad SPI's empty receive FIFO, and 0xFFFFFFFF written to the IIC or Quad SPI soft-reset word (the documented value was not tried). A design that mixes them with
  our `split` blocks has two answers for "unmapped" on one bus; an error-capture register in our block will not see
  accesses that land in an AMD IP's holes.
- **Some windows alias.** AXI GPIO repeats GIER, ISR and IER three more times in 0x100-0x1FF; AXI IIC acts on 0x100-0x17F for
  writes at 0x180-0x1FF; the AXI DMA register block repeats eight times in its 1 KB window. A stray address inside the
  window is not a hole: it is a real register.
- **Byte strobes are ignored** by every peripheral that has the port (and the DMA register port has none). A byte-lane
  read-modify-write from a CPU is safe only if the CPU always writes whole words.
- **Both AW and W must be present** before the peripherals and SmartConnect accept either channel; the AXI Interconnect takes AW
  alone. A master must not wait for AWREADY before raising WVALID (it already must not, by the AXI specification).
- **Read side effects exist:** the UART Lite pops its receive FIFO on a read of the word (and on a read at byte offset 1
  to 3 of it), and clears its overrun and frame error bits on a read of STAT. Our house rule forbids both.
- **The AXI DMA register port accepted two writes before returning the first response and returned one response for the
  two.** Both writes took effect and the port recovered afterwards. A master that pipelines two writes to it, such as an
  interconnect that does not wait for a response, would wait for a response that never comes (not tried behind an interconnect). Issue one write at a time.
- **Interrupts differ:** the UART Lite output is a one-clock pulse (two pulses per character here: receive FIFO non-empty,
  transmit FIFO empty), not a level; the GPIO output is a level 9 clocks after an input edge (a four-stage synchroniser),
  cleared by a toggle-on-write ISR; the Timer and INTC outputs are levels.
- **Same-clock set against clear:** the Timer's clear beats the hardware set (the rollover event is lost at the coincident
  clock); the INTC's acknowledge beats an input edge at the estimated coincident clock and the next one; the GPIO keeps the
  event, as our convention does. All three verdicts hold only if the coincident-clock estimate is exact to one clock. The first two differ from our convention.
- **No snapshot for a 64-bit value:** the Timer's cascade reads as two words and a read across the carry tears (4 of 12 low-first and 7 of 12 high-first trials showed an out-of-order value). Read the high word, the low word and the high word again until the high word repeats.
- **Interconnects** answer DECERR for an address outside every slave, for reads and writes, take the write data
  and keep working; the read data is a constant that differs between them (0xDEC0DEE3 for SmartConnect, 0xDEC0DE1C for the AXI Interconnect). A
  slave's own SLVERR passes through unchanged, in order with the other slave's responses.

## Against the product guides (editions held locally)

| IP | Guide held | Agrees | Disagrees or says nothing |
|---|---|---|---|
| AXI GPIO 2.0 | PG144 v2.0, January 30, 2026 | holes read 0 and writes have no effect; WSTRB ignored and both AWVALID and WVALID needed; the ISR toggles on write; a level interrupt; reserved bits read 0 | **disagrees:** the guide says an output bit of the data register reads 0; the measurement reads back the value written (probe `data_all_out`: wrote 0xC3 with all bits output, read 0xC3). Silent: the aliases at +0x40, +0x80, +0xC0 in the upper half, and the 9-clock input-to-interrupt delay |
| AXI UART Lite 2.0 | PG142 v2.0, April 5, 2017 (an old edition: no 2026 edition is held) | SLVERR for an empty RX FIFO and a full TX FIFO; a TX FIFO read and a CTRL read give 0; STAT error bits clear on read; the rising-edge interrupt at RX non-empty and TX empty; WSTRB ignored | the data of an empty-FIFO read is "undefined": measured X at reset and stale data afterwards (unexplained) |
| AXI Timer 2.0 | PG079 v2.0, August 15, 2025 | holes OKAY with 0 and no effect; WSTRB ignored; T0INT cleared by writing 1; ENALL sets both enables and writing 0 clears only ENALL; the 64-bit read recipe (high, low, high again) | silent: the clear winning over a same-clock rollover |
| AXI Interrupt Controller 4.1 | PG099 v4.1, July 15, 2021 (an old edition) | ISR writable by software until HIE is set; lowest bit has the highest priority (IVR) | silent: the acknowledge window, the latched level input |
| AXI IIC 2.1, AXI Quad SPI 3.2 | no guide held | not compared | the records stand alone |
| AXI DMA 7.1 | PG021 v7.1, June 24, 2025 | a lite write is not affected by WSTRB, and AWVALID and WVALID should be asserted together | **silent and wrong in effect:** the register window aliases eight times, a read at byte offset 1 to 3 returns 0, and a second write accepted before the first response gets no response of its own |
| SmartConnect 1.0 | PG247 v1.0, June 24, 2026 | DECERR for an address no slave is mapped to, and the offending write is not propagated | silent: the read data of the DECERR |
| AXI Interconnect 2.1 | PG059 v2.1, December 19, 2025 | DECERR for an unmapped address | silent: the read data of the DECERR; AW alone accepted |

## Records

| File | What |
|---|---|
| `gpio.json`, `uartlite.json`, `timer.json`, `intc.json`, `iic.json`, `qspi.json`, `dma.json`, `smartconnect.json`, `axi_interconnect.json` | one record per IP: the IP version (`meta.vlnv`), the configuration (`meta.config`), Vivado version, the bench and its hash, and every probe line with its result and the protocol checker's rule mask since the previous probe (`chk`) |

The versions measured are AXI GPIO 2.0, UART Lite 2.0, Timer 2.0, Interrupt Controller 4.1, IIC 2.1, Quad SPI 3.2, DMA 7.1,
SmartConnect 1.0 and AXI Interconnect 2.1, all on Vivado 2026.1 Basic, each with `REQUIRES_LICENSE 0` in the catalogue. No IP was refused. One
tool limit: `create_ip` for the AXI Interconnect fails with "IP 'xilinx.com:ip:axi_interconnect:2.1' is only supported in IP
Integrator", so both interconnects were measured inside a block design with a GPIO and a UART Lite behind them. The AXI4-Lite
protocol checker saw no rule broken in any probe of any IP (every `chk` is 0x000).

## Reproduce

Needs a local Vivado 2026.1. Each record is one `python3 amd_ip_probe/run_probe.py <ip> --record results/69_amd_ip_conventions/<ip>.json`
(IP names: gpio, uartlite, timer, intc, iic, qspi, dma, smartconnect, axi_interconnect) under a heavy slot and
`systemd-run --user --scope -p MemoryMax=4G`; each takes about 1 to 3 minutes (the DMA about 2) and well under 2 GB. xsim is not available
in CI, so CI cannot re-run them: it checks that the records, the table and the agent note agree
(`python -m pytest -q amd_ip_probe/tests`). After a re-run, `python3 amd_ip_probe/summarise.py --write` rewrites the table.

## Known gaps and limits

- Behavioural simulation on `xc7a100tcsg324-1` only, no board, no implementation. The RTL of these IP is family-independent
  where it uses no primitive, but the other families were not checked; do not read a row as holding for every family.
- Interconnect ordering was not exercised (one request at a time). The IIC and DMA alias scans also list changes of the TX FIFO read word (0x108 in IIC), probably an X comparison; the aliases cited do not depend on it. Hole writes mean 'no listed register changed'.
- Same-clock priority is placed by an estimate: the coincident clock is the clock where the interrupt output would rise and fall
  together, computed from two measured delays and the assumption that the flag reaches the output through the same path in both
  directions. The sweeps show a single transition and no intermediate value; the Timer's and the INTC's results are consistent with
  their sources (a flag flop whose reset beats its set; an acknowledge pulse with priority over the set), the GPIO's was not
  checked against its source.
- Peripherals were probed at the register port only. Not run: a transfer on any serial or memory-mapped side (UART
  Lite was looped back to itself), so the IIC, Quad SPI and DMA status, interrupt and clear behaviour, and the receive FIFO pop of the
  IIC and Quad SPI, are not measured (cells marked `?`).
- One configuration of each IP. The window size, the number of registers and some behaviours change with the generics
  (the INTC's IVAR needs fast mode, the GPIO's single channel has no interrupt registers).
- Byte-strobe forwarding by the interconnects could not be observed: both slaves behind them ignore WSTRB.
- AXI4-Lite only. Bursts, IDs and the full AXI4 behaviour of SmartConnect were not probed (brief 69 scope).
- Product guides: PG090 (IIC), PG153 (Quad SPI) and PG034 (CDMA) are not held; the UART Lite and INTC guides are old editions.
  The AXI CDMA was not probed (the DMA register port was chosen).
- The protocol checker has no rule for a missing response, so it did not flag the AXI DMA's lost response; a count of
  outstanding writes against responses at idle would. That is a follow-up to the checker.
