# P6: glitch-free clock multiplexer (natural-language spec)

*Written as a user would write it, for a Kria KR260 on my desk. Design ID register 0x000 reads 0x20960001.*

I want to switch a clock between two sources while it runs, from the PC, without glitches, and prove that the logic behind it never notices.

- Clock A is the 25 MHz C3 clock. Clock B is the 156.25 MHz GT reference clock (the SFP+ cage's MGTREFCLK0), used as it is or divided by a whole number from 1 to 8 as suits the device (the design tells me the divide).
- A glitch-free clock multiplexer (a BUFGCTRL-style one) chooses which of the two clocks drives a small block of logic, the muxed domain. I choose by a register and can see which clock is actually selected.
- The muxed domain holds a free-running counter and checks itself: the counter has an independently coded twin (for example Gray or LFSR coded) and they are compared on every clock; any disagreement, or a count that is not exactly one more than the one before, adds to an error count. The error count must stay at zero through any number of switches.
- A frequency measurement of the muxed clock: count its rising edges over a gate that is a number of C3 cycles (default 25,000,000, one second).
- A count of the switches the design carried out.

Registers (from 0x010):

| Addr | Name | Access | Meaning |
|---|---|---|---|
| 0x010 | SEL | RW | bit 0: 0 = clock A, 1 = clock B (reset 0) |
| 0x014 | STATUS | RO | bit 0 SWITCHING (a change is in progress), bit 1 ACTIVE_SEL (the clock that is actually driving the muxed domain) |
| 0x018 | B_DIV | RO | the divide applied to the GT reference clock for clock B (1 to 8) |
| 0x01C | GATE_LEN | RW | gate length in C3 cycles, default 25,000,000 |
| 0x020 | FREQ_CTRL | RW | bit 0 START (self-clearing) |
| 0x024 | FREQ_STATUS | RO | bit 0 BUSY, bit 1 DONE |
| 0x028 | FREQ_COUNT | RO | muxed-clock edges counted in the last gate |
| 0x02C | MUX_ERRS | RO | error count of the muxed domain |
| 0x030 | MUX_COUNT | RO | the muxed-domain counter's low 32 bits at the last SNAPSHOT |
| 0x034 | SWITCH_COUNT | RO | switches carried out since configuration |
| 0x038 | SNAPSHOT | WO | any write latches MUX_COUNT |

**How I check it:** the script switches 1,000 times in random order at random intervals, waiting each time until ACTIVE_SEL is the one asked for, measures the frequency after every 100th switch, and at the end checks MUX_ERRS is zero and SWITCH_COUNT equals the number of real changes.

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
