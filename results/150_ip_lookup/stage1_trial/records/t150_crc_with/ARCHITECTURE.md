# CRC-32 checker (crc32_checker) - architecture

Board: nexys_a7_100t, part xc7a100tcsg324-1. Single clock domain, 100 MHz, no MMCM.
Top module: `crc32_top` (the board top, per spec.yaml `top:`).

## Block diagram

```text
 host PC --USB-UART--> UART_TXD_IN --> +-----------------------------+
                                       |  fpga_shell (test shell)    |
 host PC <--USB-UART-- UART_RXD_OUT <--|  regs 0x00-0x05, window     |
                                       +--------------|--------------+
                                          win_addr/win_wr/win_rd/
                                          win_wdata/win_rdata
                                       +--------------v--------------+
 CPU_RESETN -> ~ -> rst -------------> |  crc32_core                 |
 CLK100MHZ  -> clk ------------------> |  crc_state (32b, reset      |
                                       |   0xFFFFFFFF), 32-bit CRC   |
                                       |   absorb, ID/DATA/CRC/CTRL  |
                                       +--------------|--------------+
                                                      v
                                             LED[15:0] = ~crc_state[15:0]
```

Window map (test shell ADDR = 0x80 + spec offset; win_addr = spec offset):

| Host ADDR | win_addr | Name | Access | Value |
|---|---|---|---|---|
| 0x80 | 0x00 | ID | RO | 0x43524333 ("CRC3") |
| 0x84 | 0x04 | DATA | WO | write absorbs 4 bytes (byte 0 = wdata[7:0]); read 0 |
| 0x88 | 0x08 | CRC | RO | ~crc_state |
| 0x8C | 0x0C | CTRL | WO | bit 0 set -> crc_state = 0xFFFFFFFF; reads 0 |

Undefined window offsets: writes ignored, reads 0.

## Clock plan

- `clk`: CLK100MHZ (pin E3), 100 MHz, one domain, no derived or gated clocks, no crossings.
- All registers (crc_state, shell window read data, LED register) are on `clk`.

## Reset plan

- `rst_n`: CPU_RESETN (pin C12), active low at the port. Inverted once in `crc32_top` into
  active-high `rst`, which feeds fpga_shell (`rst`, synchronous, active high) and crc32_core.
- Synchronous everywhere. No asynchronous reset, no synchroniser module (none needed: single domain).
- Reset only the control state: crc_state (required to reset to 0xFFFFFFFF) and the shell's own control.
  The window read-data register is not reset (its value is only meaningful after a read strobe).

## Pin list (board resource -> top port; pins from the master XDC, mapped by board_constraints)

| Board resource | Top port | Direction | Note |
|---|---|---|---|
| CLK100MHZ (E3) | CLK100MHZ | in | 100 MHz oscillator; spec name `clk` |
| CPU_RESETN (C12) | CPU_RESETN | in | active low reset; spec name `rst_n` |
| LED[15:0] (H17 K15 J13 N14 R18 V17 U17 U16 V16 T15 U14 T16 V15 V14 V12 V11) | LED[15:0] | out | LED[0] = LED0; spec name `led` |
| UART_TXD_IN (C4) | UART_TXD_IN | in | host -> FPGA (fpga_shell uart_rx) |
| UART_RXD_OUT (D4) | UART_RXD_OUT | out | FPGA -> host (fpga_shell uart_tx) |

BTNC is not used. Shell-internal bus signals have no board pin (see OQ-1).
Port names follow the master XDC (CLK100MHZ, CPU_RESETN, LED): check_constraints (FDA-CON-7)
rejects the spec's lower-case names on a board pin. The spec names (clk, rst_n, led) are kept
in the RTL-facing text above for the owner to confirm (OQ-3).

## Timing constraints (design.xdc)

- `create_clock` on CLK100MHZ, 10 ns.
- CPU_RESETN and UART_TXD_IN are asynchronous inputs: `set_false_path` from them (no delay invented).
- LED[*] and UART_RXD_OUT are outputs with no capture clock: `set_false_path` to them.

## Predicted resources

LUT 150-700 (spec estimate 220 for the CRC network and decode, plus the shell UART and framing),
FF 80-400 (spec estimate 80, plus shell), BRAM 0, DSP 0.

## CRC engine

- One 32-bit word absorbed per clock: crc_state_next = F(crc_state ^ word), F = 32 reflected
  shift steps with poly 0xEDB88320. Byte 0 (wdata[7:0]) is first in the stream, LSB first, which
  is the standard reflected CRC-32 byte order.
- Update only on a DATA write strobe (window write, win_addr 0x04), one clock after the strobe.
- CTRL write with bit 0 set loads 0xFFFFFFFF one clock after the strobe (sync clear, same clock as reset priority).
- Readback = ~crc_state. Empty stream reads 0x00000000.

## Library entries considered

- `crc32_step` (ip_lookup, search with xc7a100tcsg324-1, 10 ns): NOT taken. Its `word` variant
  (one word per clock, latency 1, 95 LUT / 33 FF) has no measured Fmax on this part, so it is
  reported as not fitting; its `byte` variant fits but takes 4 clocks per word (II 4), which
  breaks the one-clock DATA-absorb latency in spec.yaml (REQ-02). The CRC engine is written fresh.
- fpga_shell (test shell, shell/rtl/fpga_shell.sv): taken as the UART window, required by the flow.
- No FIFO or clock-crossing block is needed (single domain, no crossings).

## Open questions for the owner

- OQ-1: spec.yaml lists shell_wr_en, shell_rd_en, shell_addr, shell_wdata, shell_rd_valid,
  shell_rdata as ports of crc32_top, while the board top must instantiate fpga_shell and drive those
  signals from its window. Proposed: keep them as internal nets in crc32_top (fed from fpga_shell
  win_* through crc32_core), and amend the spec port list to drop them from the top. Until the owner
  decides, FDA-CON-8 will report these ports as missing or unconstrained.
- OQ-2: DESIGN_ID given to fpga_shell is 0x43524333 ("CRC3"), the same as the window ID. Confirm.
- OQ-3: spec.yaml names the top ports clk, rst_n and led; the master XDC names them CLK100MHZ,
  CPU_RESETN and LED, and check_constraints requires the master names on board pins. Proposed: the
  top uses the master names. Confirm, or amend spec.yaml.
- OQ-4: timing on the asynchronous pins. No input or output delay is invented for CPU_RESETN,
  UART_TXD_IN, LED and UART_RXD_OUT; they are false-pathed. Confirm this is acceptable for the
  post-synthesis unconstrained-endpoint gate.

## Status

design.xdc written with board_constraints (pins and clock from the master XDC) and timing lines;
check_constraints passes with no findings. RTL is not written; it waits on owner approval of this
document and architecture.yaml.
