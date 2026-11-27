# P2: ROM, RAM and a memory test (natural-language spec)

*Written as a user would write it, for a Kria KR260 on my desk. Design ID register 0x000 reads 0x20920001.*

I want to prove that block RAM contents survive configuration exactly, and that the memory itself is sound.

- A ROM of 1,024 words of 32 bits, filled from `data/rom_init.hex` (one hex word per line) when the FPGA is configured (read the file with `$readmemh`).
- A RAM of 1,024 words of 32 bits. Its power-up contents must be defined: word *i* holds 0xC0DE0000 + *i* straight after configuration, before anyone writes to it.
- The host reads and writes both memories one word at a time through an address register, with an optional auto-increment.
- A memory test that runs on the chip by itself, so it runs at full speed: the classic **March C-** over the whole RAM, with all-zero and all-one words as the backgrounds,
  for a number of passes I choose. It counts the words that read back wrong, and remembers the address of the first one. A control bit injects a fault on purpose (the test then expects a
  wrong value at one address each pass), so I can see the test notices errors.

Registers (from 0x010):

| Addr | Name | Access | Meaning |
|---|---|---|---|
| 0x010 | MEM_ADDR | RW | word address, 10 bits |
| 0x014 | ROM_DATA | RO | the ROM word at MEM_ADDR; with AUTOINC, a read then adds 1 to MEM_ADDR (wraps at 1,024) |
| 0x018 | RAM_DATA | RW | read or write the RAM word at MEM_ADDR; with AUTOINC, each access then adds 1 to MEM_ADDR |
| 0x01C | MEM_CTRL | RW | bit 0 AUTOINC |
| 0x020 | MARCH_CTRL | RW | bit 0 START (self-clearing; clears the counters), bit 1 INJECT_FAULT |
| 0x024 | MARCH_PASSES | RW | number of passes, 1 to 65,535 |
| 0x028 | MARCH_STATUS | RO | bit 0 BUSY, bit 1 DONE, bits 31:16 passes completed |
| 0x02C | MARCH_ERRS | RO | words that read wrong, since START |
| 0x030 | MARCH_FIRST_ERR | RO | address of the first wrong word, 0xFFFFFFFF if none |

**How I check it:** straight after programming, before any write, the script reads all 1,024 ROM words and all 1,024 RAM words and compares them with the file and with 0xC0DE0000 + *i*.
Then it writes and reads back some patterns, runs the March test for 200 passes with no fault (zero errors expected), and runs it for 3 passes with the fault injected (errors expected). Afterwards the RAM must hold all zeros, which is where March C- leaves it.

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
