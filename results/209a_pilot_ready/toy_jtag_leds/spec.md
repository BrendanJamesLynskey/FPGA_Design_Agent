# Toy: two registers and an LED blink (natural-language spec)

*Written as a user would write it, for a Kria KR260 on my desk. Design ID register 0x000 reads 0x20920001.*

I want a first design to prove the JTAG route works on this board. It has two registers of its own and blinks an LED.

- LED 0 blinks from the 25 MHz clock: it toggles every BLINK_DIV clock cycles. The default is 12,500,000 cycles, so it blinks at 1 Hz.
- LED 1 shows whether the blink is enabled: on when enabled, off when not.
- The blink is off after reset until I enable it. While it is off, LED 0 is off.

Registers (from 0x010):

| Addr | Name | Access | Meaning |
|---|---|---|---|
| 0x010 | BLINK_DIV | RW | clock cycles per LED 0 toggle, 1 to 2^32-1, default 12,500,000; a write of 0 is stored as 1 |
| 0x014 | CTRL | RW | bit 0 BLINK_EN (default 0); the other bits read 0 and ignore writes |

**How I check it:** the script reads the ID and BUILD registers, writes and reads back the scratch register, writes a few values to BLINK_DIV and CTRL and
reads them back (including 0, which must read back 1), and leaves both at their reset values.

## How I talk to it

There is no UART on this board. I reach the design from the PC over the JTAG cable, through the register bus module in
`data/jtag_bus.sv` (the one we already use on this board; please copy it into the design unchanged). It gives the design a simple
register port in the clock domain of the `clk` you give it (a free-running clock; hold `rst` for a few clocks at start):
`h_we` and `h_re` pulses, `h_addr[11:0]` (byte addresses), `h_wdata[31:0]` and `h_rdata[31:0]`. All registers are 32 bits on 4-byte steps.
A write takes effect the clock after `h_we`. After `h_re`, `h_rdata` must show the addressed register within 2 clocks and hold it. Unmapped
addresses read 0 and ignore writes. The module contains Xilinx primitives, so the simulation need not include it: test the register port
directly.

Registers every one of my designs has:

| Addr | Name | Access | Meaning |
|---|---|---|---|
| 0x000 | ID | RO | the design ID given above |
| 0x004 | BUILD | RO | the bitstream's USR_ACCESS word (the USR_ACCESSE2 primitive); I check it against the build record before every test |
| 0x008 | SCRATCH | RW | 32 bits, reads back what was written, resets to 0 |

The board is the Kria KR260 (K26). The two user LEDs are `led[1:0]`. The 25 MHz clock is the C3 pin. If the design drives the SFP+
`sfp_tx_disable` pin, it holds it at 1 (laser off) at all times, and it uses no GT transceiver channel.
