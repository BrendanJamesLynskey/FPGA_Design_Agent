# Register map (trigger_core)

32-bit registers, word addresses 0x000..0xFFF. On the board the host reaches them over the JTAG cable
(`rtl/jtag_bus.sv`, `host/jtag_regs.tcl`); the cocotb tests drive the bus directly. A read returns data two clocks
after the address (the histogram RAMs need the first). RO = read only; P = pulse (write 1, clears itself).

## Control and status

| Address | Name | Bits |
|---|---|---|
| 0x000 | ID (RO) | 0x58A00001 |
| 0x001 | BUILD_STAMP (RO) | first 8 hex digits of the sources' SHA-256 (the flow sets it) |
| 0x002 | CTRL | [0] core enable, [1] speculative (1, default) or safe (0), [2] halt on sequence gap, [3] kill, [4] histogram A metric (0 RX SFD to first preamble byte, 1 decision to first preamble byte), [5] hold both PHYs in reset |
| 0x003 | PULSE (P) | [0] clear counters, [1] clear book, [2] clear histograms, [3] clear halt, [4] clear the latched kill input, [5] commit the rule table, [6] pop the decision log, [7] soft reset of the order slot (board-safe): drops an order that has not started and a pending ARP reply; never an undo: an order already started is still poisoned or cancelled if its frame turns out bad, and a pending cancel is still sent |
| 0x004 | STATUS (RO) | [0] kill in force, [1] halted, [2] kill input latched, [3] DRP busy, [4] MDIO B busy, [5] MDIO A busy, [6] histogram clearing, [7] book clearing |
| 0x005 | TS (RO) | the free-running 125 MHz counter (8 ns) |
| 0x006 | RULES_VERSION (RO) | commits since reset |
| 0x007 | COMMIT_TS (RO) | TS at the last commit (the tick-to-config end point) |
| 0x008 | BUILD_MODE (RO) | 0 checksum computed before the decision, 1 after it (both streamed as the MAC asks), 2 store and assemble then send |
| 0x009 | ORDER_SLOT (RO) | [0] slot busy, [2] granted, [3] verdict known, [4] verdict good, [5] started, [6] sent, [7] cancel pending, [23:16] the slot's frame number, [31:24] frames received (both mod 256) |

## Addresses and ports (defaults are locally administered example values)

| Address | Name | Default |
|---|---|---|
| 0x010/0x011 | board MAC [47:16] / [15:0] | 02:00:00:00:58:0a |
| 0x012 | board IPv4 | 192.168.58.10 |
| 0x013 | board UDP port | 5800 |
| 0x014/0x015 | venue MAC [47:16] / [15:0] | 02:00:00:00:58:0f |
| 0x016 | venue IPv4 | 192.168.58.15 |
| 0x017 | venue UDP port | 5801 |

## Interlocks

| Address | Name | Default |
|---|---|---|
| 0x020 | MAX_QTY | 100 |
| 0x021 | BAND (hundredths; the order price against the book before the triggering message) | 500 |
| 0x022 | MAX_POS (position limit, counted since reset) | 1000 |
| 0x023 | BUCKET (writing it refills the bucket) | 16 |
| 0x024 | REFILL (clocks per token) | 125000 (1 ms) |
| 0x025 | PIN_WIDTH (clocks a pin stays high) | 12,500,000 (100 ms) |
| 0x026 | POSITION (RO, signed) | |
| 0x027 | TOKENS (RO) | |
| 0x028 | EXPECTED_SEQ (RO) | |

## Book (read)

0x030 selects an instrument; 0x031..0x035 read its entry: bid price, bid size, ask price, ask size, last trade price.

## Rule table

0x040 + 8 x rule + word (rules 0..7, words 0..5): writes go to a shadow table, reads return the active table;
PULSE[5] copies the shadow into the active table in one clock. Layout: `docs/rule_table.md`.

## Counters (RO, 32-bit, cleared by PULSE[0])

0x100 + index, in the order of `model/ref_model.py` `COUNTERS`:

| Index | Counter | Index | Counter |
|---|---|---|---|
| 0 | port A frames received | 26-31 | refused: kill, halt, size, band, position, rate |
| 1 | good frames | 32 | requests suppressed (one order per frame) |
| 2 | bytes received | 33 | requests refused: order slot busy |
| 3 | FCS errors | 34 | speculative orders dropped before sending |
| 4 | runts (< 64 bytes) | 35 | speculative orders poisoned on the wire |
| 5 | giants (> 1522 bytes) | 36 | speculative orders cancelled after sending |
| 6 | frames with RX_ER | 37 | orders dropped by kill |
| 7 | bytes before an SFD that were not preamble | 38 | orders sent |
| 8-14 | dropped: MAC, EtherType, IPv4, IP checksum, UDP port, feed header, ARP | 39 | cancels sent |
| 15 | ARP requests for us | 40 | ARP replies sent |
| 16 | feed packets | 41 | port A frames sent |
| 17 | messages | 42 | port A frames sent with a poisoned FCS |
| 18 | sequence gaps | 43 | port A receive FIFO overflows |
| 19 | book mismatches | 44-46 | port B frames received, good, FCS errors |
| 20 | instruments outside the book | 47 | orders received back on port B |
| 21 | unknown message types | 48 | feed packets sent by port B's generator |
| 22 | rule firings | 49 | port B frames sent |
| 23 | matches held off | 50 | port B receive FIFO overflows |
| 24 | requests to the interlocks | 51 | decision-log entries lost (log full) |
| 25 | grants | 52 | watchdog undos (no verdict within 4096 clocks: treated as a bad frame) |
| | | 53 | order-slot resets (PULSE[7]) |

## Decision log, histograms, management

| Address | Name |
|---|---|
| 0x140 | log entries waiting (RO) |
| 0x141..0x144 | the oldest entry: TS of the decision, message sequence, {table version [31:16], rule [14:12], instrument [11:0]}, order price; PULSE[6] pops it |
| 0x150..0x156 | histogram A, per order, in clocks: CTRL[4] = 0 from the SFD taken by the receive MAC, 1 from the decision clock, to the order's first preamble byte leaving the transmit MAC (core side, not the pins): count, sum [31:0], sum [47:32], min, max, lost, last |
| 0x158..0x15E | histogram B (port B loop: generator's first preamble byte out to the order's SFD back): the same |
| 0x400..0x4FF | histogram A bins, 1 clock (8 ns) each; the last bin also holds everything above |
| 0x500..0x5FF | histogram B bins |
| 0x180 / 0x182 | MDIO A / B command (write starts it): [30] read, [25:21] PHY address, [20:16] register, [15:0] write data |
| 0x181 / 0x183 | MDIO A / B result: [31] busy, [15:0] read data |
| 0x184 / 0x185 | port A / B RX_CLK edge count (to check the 125 MHz receive clock against TS) |
| 0x1A0 | SYSMON (the on-chip temperature and supply monitor) DRP (its register port): write [31] write, [23:16] address, [15:0] data; read [31] busy, [15:0] data |
| 0x1A1 / 0x1A2 | SYSMON alarms now / latched since the last write to 0x1A2 |
| 0x1C0..0x1CC | port B generator: enable, interval (clocks), packets (0 = no end), messages per packet, instrument mask, base price, price mask, {bad FCS every [31:16], gap every [15:0]}, source MAC (2), source IPv4, source port, packets sent (0x1CC, RO) |
