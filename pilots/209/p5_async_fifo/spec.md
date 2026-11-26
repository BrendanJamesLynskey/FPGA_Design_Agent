# P5: asynchronous FIFO soak (natural-language spec)

*Written as a user would write it, for a Kria KR260 on my desk. Design ID register 0x000 reads 0x20950001.*

I want a long-run test of data crossing between two clocks that are not related: the writer runs on the 25 MHz C3 clock, the reader on the 156.25 MHz GT reference clock (the SFP+ cage's MGTREFCLK0). An asynchronous FIFO of 512 words of 32 bits sits between them.

- The writer produces a pseudo-random binary sequence (PRBS-31, x^31 + x^28 + 1, 32 new bits per word, non-zero seed 0x7FFFFFFF) and writes one word on every writer clock while the FIFO is not full.
- The reader takes words out whenever the FIFO is not empty and checks each against its own copy of the same sequence, started from the same seed when RUN begins.
- Counters: words written, words read and checked, data errors, overflows (a write while full, which must never happen), underflows (a read while empty, which must never happen), cycles the writer was held off because the FIFO was full, and the highest FIFO fill seen.
- A SLOW_READ control bit makes the reader take only one word in eight clocks, so the FIFO fills and the writer is held off. A control bit INJECT flips one bit of one received word before the check, once, so I can see the checker notices.
- A SNAPSHOT write latches all counters at one instant, so that the values I read together belong together. The counters wrap at 32 bits.

Registers (from 0x010):

| Addr | Name | Access | Meaning |
|---|---|---|---|
| 0x010 | CTRL | RW | bit 0 RUN, bit 1 SLOW_READ, bit 2 CLEAR (self-clearing; counters and the sequences restart; only while RUN is 0), bit 3 INJECT (self-clearing; one flipped word) |
| 0x014 | WORDS_W | RO | words written (snapshot) |
| 0x018 | WORDS_R | RO | words read and checked (snapshot) |
| 0x01C | DATA_ERRS | RO | words that did not match (snapshot) |
| 0x020 | OVERFLOWS | RO | (snapshot) |
| 0x024 | UNDERFLOWS | RO | (snapshot) |
| 0x028 | STALL_W | RO | writer clocks held off by a full FIFO (snapshot) |
| 0x02C | OCC_MAX | RO | highest fill seen, in words (snapshot) |
| 0x030 | SNAPSHOT | WO | any write latches 0x014 to 0x02C |

**How I check it:** after a short check with INJECT and SLOW_READ, the script clears, runs for 10 minutes with a snapshot every 10 seconds, and wants zero data errors, overflows and underflows, and the word counts moving at the clock rate. I will not call it good from a one-second test: the CDC constraints in the build matter, and I want to see them.

## How I talk to it

There is no UART on this board. I reach the design from the PC over the JTAG cable, through the register bus module in
`data/jtag_bus.sv` (the one we already use on this board; please use it unchanged). It gives the design a simple
register port in the clock domain of the `clk` you give it (a free-running clock; hold `rst` for a few clocks at start):
`h_we` and `h_re` pulses, `h_addr[11:0]` (byte addresses), `h_wdata[31:0]` and `h_rdata[31:0]`. All registers are 32 bits on 4-byte steps.
A write takes effect the clock after `h_we`. After `h_re`, `h_rdata` must show the addressed register within 2 clocks and hold it. Unmapped
addresses read 0 and ignore writes. The module contains Xilinx primitives, so the simulation need not include it: test the register port
directly.

Registers every one of my designs has:

| Addr | Name | Access | Meaning |
|---|---|---|---|
| 0x000 | ID | RO | the design ID given below |
| 0x004 | BUILD | RO | the bitstream's USR_ACCESS word (the USR_ACCESSE2 primitive); I check it against the build record before every test |
| 0x008 | SCRATCH | RW | 32 bits, reads back what was written, resets to 0 |

The board is the Kria KR260 (K26). The two user LEDs are `led[1:0]`. The 25 MHz clock is the C3 pin. If the design drives the SFP+
`sfp_tx_disable` pin, it holds it at 1 (laser off) at all times, and it uses no GT transceiver channel, at most the GT reference clock buffer.
