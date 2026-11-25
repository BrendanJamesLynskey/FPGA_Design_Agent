# P4: 32-tap FIR filter (natural-language spec)

*Written as a user would write it, for a Kria KR260 on my desk. Design ID register 0x000 reads 0x20940001.*

I want a 32-tap symmetric FIR low-pass filter in fixed point that I can feed from the PC, built on the DSP slices and fast.

- Input samples are 16-bit signed. The 32 coefficients are 16-bit signed (Q1.15) and fixed: they are in `data/coeffs.hex`, one per line, tap 0 first (they are symmetric: use that to halve the multipliers).
- Output = (sum over k of h[k] x x[n-k] + 0x4000) arithmetic-shifted right by 15, then saturated to the 16-bit signed range. The sum is exact (no intermediate rounding). Samples before the first one are 0.
- The datapath takes one sample per clock and must close timing at 250 MHz or faster (make a clock for it from the 25 MHz board clock; the register bus can stay on its own clock).
- An input FIFO of 1,024 samples that I fill, an output FIFO of 1,024 samples that I drain. A RUN command processes everything that is in the input FIFO, in order, and puts the results in the output FIFO. The filter's history stays between runs until I clear it, so I can send a long signal in chunks and get the same result as sending it in one go.
- A count of the outputs that saturated.

Registers (from 0x010):

| Addr | Name | Access | Meaning |
|---|---|---|---|
| 0x010 | CTRL | RW | bit 0 CLEAR (self-clearing: empties both FIFOs, zeroes the filter history and the counters), bit 1 RUN (self-clearing: process the input FIFO) |
| 0x014 | IN_PUSH | WO | push the low 16 bits as a sample (ignored when the input FIFO is full) |
| 0x018 | OUT_POP | RO | bit 31 = 1 and bits 15:0 = the oldest output, which is removed by the read; bit 31 = 0 and 0 otherwise when the FIFO is empty |
| 0x01C | STATUS | RO | bit 0 BUSY, bits 15:4 input FIFO count (0 to 1,024), bits 31:20 output FIFO count |
| 0x020 | SAT_COUNT | RO | outputs that saturated since CLEAR |
| 0x024 | SAMPLES_DONE | RO | samples processed since CLEAR |

**How I check it:** the script compares every output bit for bit with a Python model of the formula above, for an impulse, a step, and 10,000 random samples sent in chunks of 1,000 with no CLEAR between them. I also want the build report to show the DSP slices used and the clock the datapath met.

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

- data/coeffs.hex (160 bytes)
- data/jtag_bus.sv (3341 bytes)

Simulations and the Vivado build run with these files available: `$readmemh("data/<name>")` and `$readmemh("<name>")` both open them, and the scoring run finds them the same way. A design may read them with $readmemh/$readmemb or embed their values in the RTL.
