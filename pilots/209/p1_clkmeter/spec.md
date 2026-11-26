# P1: clock frequency meter (natural-language spec)

*Written as a user would write it, for a Kria KR260 on my desk. Design ID register 0x000 reads 0x20910001.*

I want to know what frequency the 25 MHz clock on pin C3 really runs at. Nobody has measured it. The board also has a 156.25 MHz reference
clock for the SFP+ cage (the GT reference clock, MGTREFCLK0 of the SFP quad). I trust its frequency more, so use it as the ruler: count the
rising edges of the C3 clock over a gate that is a fixed number of cycles of the 156.25 MHz clock. The default gate is 156,250,000 cycles (one second).

- The gate length is set by a register (default one second, minimum 1,000 cycles). Writing the start bit runs one measurement.
- When it is done I read how many C3 edges were counted, and how many reference cycles the gate actually lasted (it must equal the gate length I asked for).
- A counter of completed measurements, so I can see it ran.
- LED 0 blinks at about 1 Hz from the C3 clock, LED 1 at about 1 Hz from the reference clock, so I can see both clocks are alive. A control bit turns both LEDs off, and
  they are off after reset until I turn them on.

Registers (from 0x010):

| Addr | Name | Access | Meaning |
|---|---|---|---|
| 0x010 | GATE_LEN | RW | gate length in reference-clock cycles, default 156,250,000 |
| 0x014 | CTRL | RW | bit 0 START (self-clearing; ignored while busy), bit 1 LED_EN (default 0) |
| 0x018 | STATUS | RO | bit 0 BUSY, bit 1 DONE (cleared by START, set when the result registers are valid) |
| 0x01C | COUNT | RO | C3 rising edges counted in the last completed gate |
| 0x020 | GATE_ACTUAL | RO | reference cycles in the last completed gate |
| 0x024 | MEAS_DONE | RO | number of completed measurements since configuration |

**How I check it:** the script runs five one-second measurements and a few shorter ones with other gate lengths, and computes the frequency as
COUNT x 156.25 MHz / GATE_ACTUAL. I expect 25 MHz within 100 ppm (the two oscillators are both only crystals). I also check GATE_ACTUAL equals the gate I set, and that the five readings agree with each other closely. The reading is for the board file, so it matters.

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
