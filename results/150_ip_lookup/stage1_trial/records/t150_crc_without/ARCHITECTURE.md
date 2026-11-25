# CRC-32 checker over the UART test shell (crc32_checker)

Board: Nexys A7-100T (xc7a100tcsg324-1). Top module: `crc32_top`.

Purpose: accept 32-bit data words from a host over the UART test shell, fold each word into a
reflected CRC-32 (IEEE 802.3, POLY 0xEDB88320, INIT 0xFFFFFFFF) in one clock, read the finalised
CRC back, clear it, and show CRC[15:0] on the 16 LEDs. Design ID reads `CRC3` (0x43524333).

## Block diagram

```text
                 CLK100MHZ (100 MHz)
                    |
  CPU_RESETN ->  reset_sync --- rst (active high) ----------------------+
  (async assert,       |                                                |
   sync release)       |                                                v
                       |   UART_TXD_IN (uart_rxd) -> sync2 -> uart_rx   fpga_shell
  host <--- USB-UART ----------------------------------- uart_tx <--- UART_RXD_OUT (uart_txd)
                                                          |
                                             window 0x80-0xFF (win_addr, win_wr, win_rd,
                                             win_wdata, win_rdata)
                                                          v
                                                     crc32_regs
                                                  ID 0x00  CRC 0x04
                                                  CTRL 0x08 (CLEAR)  DATA 0x0C
                                                          | eng_wr / eng_clear / eng_data
                                                          v
                                                     crc_engine  (32-bit state, XOR network)
                                                          | state
                                                          v
                                    CRC = state ^ 0xFFFFFFFF  ->  led[15:0] (crc32_top)
```

Blocks (see architecture.yaml):
- `crc32_top`: board top, instantiates `fpga_shell`, `reset_sync`, `crc32_regs`, `crc_engine`.
- `reset_sync`: CPU reset synchroniser (declared reset synchroniser).
- `fpga_shell`: the bank's test shell (unchanged), 115200 8N1.
- `crc32_regs`: decodes the window addresses and produces the engine strobes.
- `crc_engine`: CRC state register and the combinational 32-bit XOR network.

## Port names

Spec ports are used as named in spec.yaml; `board_constraints` maps each board resource to them:

| Port | Dir | Width | Board resource | Role |
|---|---|---|---|---|
| clk | in | 1 | CLK100MHZ | 100 MHz board clock |
| cpu_resetn | in | 1 | CPU_RESETN | reset button, active low, asynchronous |
| uart_rxd | in | 1 | UART_TXD_IN | host to FPGA (the shell's receive) |
| uart_txd | out | 1 | UART_RXD_OUT | FPGA to host (the shell's transmit) |
| led | out | 16 | LD0..LD15 | CRC[15:0] |

Both UART directions are declared and constrained (the shell uses both).

## Clock plan

- One clock domain, `clk`, 100 MHz (10 ns). Engine, shell registers, window decode and LEDs all run on it.
- No derived, gated or generated clocks. No MMCM/PLL is used.
- Timing: the 32-bit XOR network must close setup at 10 ns with no failing endpoints (REQ-10).
- Clock constraint comes from `board_constraints` (the master XDC clock on CLK100MHZ).

## Reset plan

- `cpu_resetn` is active low and asynchronous to `clk`. `reset_sync` asserts asynchronously and
  releases synchronously (two flops), producing one active-high synchronous `rst`.
- Inside the design `rst` is the only reset. Control registers take the synchronous reset (shell,
  CRC state, window decode); datapath registers (frame and response bytes, the XOR network) take no reset.
- Reset value: CRC state 0xFFFFFFFF, so CRC reads 0x00000000 and led shows 0x0000 during and after reset.

## Crossings

| From | To | Signal | Primitive | Inline in |
|---|---|---|---|---|
| async | clk | cpu_resetn | reset_sync | reset_sync |
| async | clk | uart_rxd | sync2 (two-flop) | uart_rx (shell) |

No other clock-domain crossing exists.

## Register map (window, shell ADDR = 0x80 + offset)

| Offset | Name | Access | Reset | Bits |
|---|---|---|---|---|
| 0x00 | ID | RO | 0x43524333 | design ID "CRC3" |
| 0x04 | CRC | RO | 0x00000000 | state ^ 0xFFFFFFFF |
| 0x08 | CTRL | WO (reads 0) | 0x00000000 | [0] CLEAR, self-clearing; [31:1] reserved |
| 0x0C | DATA | WO (reads 0) | 0x00000000 | [31:0] word pushed into the engine for one clock |

Window address = shell address - 0x80, so the design registers sit at shell ADDR 0x80, 0x84, 0x88, 0x8C.

Engine: a DATA write (no CLEAR) updates state on the next clock with the word, bit 0 of each byte first,
bits 7:0 as the first byte. A CTRL write with bit 0 set sets state to 0xFFFFFFFF on the next clock.
CLEAR and DATA in the same clock: CLEAR wins, the word is dropped.

## Pin list (board resources; pin numbers are held in design.xdc, written by board_constraints)

| Board resource | Port | Standard |
|---|---|---|
| CLK100MHZ | clk | set by board_constraints |
| CPU_RESETN | cpu_resetn | set by board_constraints |
| UART_TXD_IN | uart_rxd | set by board_constraints |
| UART_RXD_OUT | uart_txd | set by board_constraints |
| LD0..LD15 | led[15:0] | set by board_constraints |

## Predicted resources

- LUT: 150 to 500 (XOR network and decode about 150 to 300, shell about 100 to 200).
- FF: 200 to 400 (32 CRC state, shell frame/response bytes, counters, UART).
- BRAM tiles: 0. DSP: 0.

## Stage status

Architecture written for owner approval. RTL is not written until this document and architecture.yaml are approved.
design.xdc is not yet written: it needs `board_constraints` with the resource map above, then the I/O timing lines.
