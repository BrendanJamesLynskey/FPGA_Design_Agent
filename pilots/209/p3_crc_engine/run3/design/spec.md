# P3: CRC-32 engine (natural-language spec)

*Written as a user would write it, for a Kria KR260 on my desk. Design ID register 0x000 reads 0x20930001.*

I want an Ethernet CRC-32 engine that I feed from the PC. It is the usual CRC-32 (polynomial 0x04C11DB7, reflected, initial value 0xFFFFFFFF, final XOR 0xFFFFFFFF) of the bytes in the order I send them,
which is what Python's `zlib.crc32` gives.

- I send a message as 32-bit words, four bytes each, with the least significant byte first, and finish with a last push of 0 to 3 bytes. The message can be any length including empty.
- I can read the CRC of everything sent since the last INIT at any time, already finished (final XOR applied), and the number of bytes sent.
- A throughput counter: how many clock cycles the CRC datapath was busy since INIT. It must keep up with one 4-byte word per clock, so a message of N full words takes N busy cycles; I want to see the engine can do 4 bytes per clock at the clock you chose, and the clock rate to be at least 100 MHz.

Registers (from 0x010):

| Addr | Name | Access | Meaning |
|---|---|---|---|
| 0x010 | CTRL | RW | bit 0 INIT (self-clearing: CRC back to the start value, byte count and busy counter to 0) |
| 0x014 | PUSH4 | WO | pushes the four bytes of the written word (bits 7:0 first) |
| 0x018 | PUSH_N | WO | pushes the low N bytes of the written word (bits 7:0 first), N from TAIL_LEN |
| 0x01C | TAIL_LEN | RW | N for PUSH_N, 0 to 3 (0 pushes nothing) |
| 0x020 | CRC | RO | CRC-32 of all bytes since INIT (a message of no bytes gives 0x00000000) |
| 0x024 | BYTE_COUNT | RO | bytes pushed since INIT |
| 0x028 | BUSY_CYCLES | RO | clock cycles the CRC datapath processed data since INIT |

**How I check it:** the script sends 1,000 random messages (lengths include 0, 1, 2, 3, 4, 5, 7, 8, 63, 64, 65 and some of a few hundred bytes, then random) and compares CRC and BYTE_COUNT with `zlib.crc32` every time. It also checks BUSY_CYCLES for the full-word messages.

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


## Data files supplied with this request

These files belong to the request. They are in the design directory under data/ and are read-only (read them with read_file; list_files data shows them):

- data/jtag_bus.sv (3341 bytes)

Simulations and the Vivado build run with these files available: `$readmemh("data/<name>")` and `$readmemh("<name>")` both open them, and the scoring run finds them the same way. A design may read them with $readmemh/$readmemb or embed their values in the RTL.
