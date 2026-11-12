# Test shell protocol (version 1.0)

Every design embeds the test shell (`shell/rtl/fpga_shell.sv`) so that a host can test it over the board's
USB-UART without a debugger. This file is the shell's specification: the RTL, the Python model
(`shell/model/shell_model.py`) and the host driver (`shell/host/fpga_shell.py`) are all checked against it.

## Line

- UART, 8 data bits, no parity, 1 stop bit, LSB first, idle high.
- **115200 baud** by default: `CLKS_PER_BIT = 868` at 100 MHz (100e6 / 115200 = 868.06, an error of -0.007 %).
  The receiver samples each bit at its middle, so it tolerates a few per cent of baud mismatch; the cocotb tests
  check ±2 %.
- On the Nexys A7 the FPGA receives on `UART_TXD_IN` (pin C4) and sends on `UART_RXD_OUT` (pin D4); the names are
  from the host's point of view. RTS/CTS are not used.

## Frames

All multi-byte values are **little-endian** (D0 = bits 7:0). `CHK` is the XOR of the bytes between the sync byte
and `CHK`.

Request, always 8 bytes, read or write:

| Byte | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| | `0xA5` | CMD | ADDR | D0 | D1 | D2 | D3 | CHK = CMD ^ ADDR ^ D0 ^ D1 ^ D2 ^ D3 |

CMD: `0x01` read (the data bytes are ignored; send zeros), `0x02` write.

Response, always 7 bytes:

| Byte | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| | `0x5A` | STATUS | D0 | D1 | D2 | D3 | CHK = STATUS ^ D0 ^ D1 ^ D2 ^ D3 |

The data is the register's value for a read and the value written for a successful write (0 for a write to
STATUS). Errors return data 0.

| STATUS | Name | When |
|---|---|---|
| `0x00` | OK | |
| `0x01` | BAD_CHECKSUM | CHK does not match (checked first) |
| `0x02` | BAD_COMMAND | CMD is not 0x01 or 0x02 |
| `0x03` | BAD_ADDRESS | ADDR is 0x05-0x7F |
| `0x04` | READ_ONLY | a write to 0x00-0x02 |

## Framing and recovery rules

1. **Sync.** While idle the shell discards every byte until it sees `0xA5`; the next 7 bytes are the frame,
   whatever their values.
2. **Timeout.** If a frame stops for more than `TIMEOUT_CYCLES` clocks (100 000 = **1 ms** at 100 MHz, about 11
   byte times at 115200) between bytes, the shell drops it without answering and goes back to hunting. A host that
   gets no answer waits more than 1 ms and sends the request again.
3. **UART framing error.** A byte with a low stop bit is dropped and any part frame is abandoned (no answer).
4. **One request at a time.** The host waits for the response before sending the next request; bytes that arrive
   while the shell is still sending a response are discarded.
5. Every error above is counted in STATUS.

## Registers

| ADDR | Name | Access | Value |
|---|---|---|---|
| `0x00` | DESIGN_ID | RO | four ASCII characters chosen by the design, MSB first (the T1 design is `"T1DC"` = `0x54314443`) |
| `0x01` | SHELL_VERSION | RO | `0x00010000` (major 1, minor 0) |
| `0x02` | BUILD_STAMP | RO | set at build time; the flow puts the first 8 hex digits of the SHA-256 of the design's source and constraint files here (`flow/prepare.py`; 0 in simulation) |
| `0x03` | SCRATCH | RW | any 32-bit value; reset 0; for loopback tests |
| `0x04` | STATUS | RO, write clears | `[7:0]` checksum errors, `[15:8]` request errors (bad command, bad address, read-only), `[23:16]` UART framing errors, `[31:24]` frame timeouts; each saturates at 255; any write sets all four to 0 |
| `0x05`-`0x7F` | reserved | | BAD_ADDRESS |
| `0x80`-`0xFF` | window | design | the design under test's registers; never an error from the shell |

## The window interface (shell to design)

| Signal | Dir | Meaning |
|---|---|---|
| `win_addr[6:0]` | out | ADDR - 0x80 |
| `win_wr` | out | one-cycle pulse: write `win_wdata` to `win_addr` |
| `win_rd` | out | one-cycle pulse: read `win_addr` |
| `win_wdata[31:0]` | out | |
| `win_rdata[31:0]` | in | must be valid in the cycle after `win_rd` (register it) |

`win_addr` and `win_wdata` are stable during the pulse.

## Worked bytes (the tests check these)

| What | Request | Response |
|---|---|---|
| read DESIGN_ID of the T1 design | `A5 01 00 00 00 00 00 01` | `5A 00 43 44 31 54 62` |
| write SCRATCH = `0x12345678` | `A5 02 03 78 56 34 12 09` | `5A 00 78 56 34 12 08` |
| any request with a bad CHK | | `5A 01 00 00 00 00 01` |
| write DESIGN_ID | `A5 02 00 00 00 00 00 02` | `5A 04 00 00 00 00 04` |

A full request and its response take 15 bytes x 10 bits / 115200 = **1.30 ms** on the line, plus the host's
USB latency.
