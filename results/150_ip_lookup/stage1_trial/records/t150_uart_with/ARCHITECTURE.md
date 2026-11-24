# seg1_counter: architecture (stage 1, board and device planning)

Board: Nexys A7-100T, part xc7a100tcsg324-1. Top module `top`. One clock domain.
The design counts up once per second, shows the count on four seven-segment digits,
clears it from the centre button and exposes it (and the design ID) through the
UART test shell `fpga_shell`.

## Block diagram

```text
                      CLK100MHZ (100 MHz)
                            |
   CPU_RESETN --> [reset_sync] --> rst (active high, sync release)
                            |
   BTNC ----------> [btn_debounce] --- clr_pulse ---+
                    (sync2 + 10 ms hold)            |
                                                    v
   UART_TXD_IN --> +---------------------------+  +--------------+
                   |  fpga_shell (test shell)  |->| seg1_counter |
   UART_RXD_OUT <--|  uart_rx, uart_tx, core   |  | tick (1 s)   |
                   +---------------------------+  | count 0..9999|
                        win_addr/wr/rd/wdata      +------+-------+
                        win_rdata (ID, COUNT)           | count[13:0] (binary)
                                                        v
                                               +-----------------+
                                               | seg_display     |--> SEG[7:0] (registered)
                                               | BCD + 4-digit   |--> AN[7:0]  (registered)
                                               | scan, 1 ms slot |
                                               +-----------------+
```

Blocks (module, file):

| Name | Function |
|---|---|
| top (rtl/top.sv) | board top: resets, instantiates every block below and fpga_shell, ties AN4..AN7 high |
| reset_sync (shell) | synchronises CPU_RESETN into CLK100MHZ, active-high reset (async assert, sync release) |
| btn_debounce (rtl/btn_debounce.sv) | sync2 on BTNC, counts consecutive high cycles, one-cycle clr pulse after DEBOUNCE_CYCLES |
| seg1_counter (rtl/seg1_counter.sv) | 27-bit tick counter (ONE_SEC_CYCLES), 14-bit binary count 0..9999, clear on clr_pulse, window register map (ID at 0x00, COUNT at 0x04 as window offsets 0x80 / 0x84 are the shell's; see register map) |
| seg_display (rtl/seg_display.sv) | binary to four BCD digits (double dabble), digit scan counter (SCAN_CYCLES), segment decode, registered SEG and AN outputs |
| fpga_shell (shell) | UART 115200 8N1 line, frame protocol, register window |

## Register map (through the shell window)

The shell owns 0x00 to 0x7F. The design's registers sit in the window at 0x80 and up.
The spec's offsets are the design's offsets, so the window addresses are the shell address minus 0x80.

| Shell ADDR | Window win_addr | Name | Access | Reset | Value |
|---|---|---|---|---|---|
| 0x80 | 0x00 | ID | RO | 0x53454731 | ASCII "SEG1" (byte 3 = S) |
| 0x84 | 0x04 | COUNT | RO | 0x00000000 | bits [15:0] binary count, 0..9999; bits 31:16 = 0 |

Read-only: win_wr is ignored. The count is read live (no snapshot), as the spec defaults say.

## Clock plan

| Domain | Port | Frequency | Notes |
|---|---|---|---|
| clk | CLK100MHZ | 100 MHz (10 ns) | the only clock; tick, debounce, scan and UART all on it; no gated or derived clocks; tick is a clock-enable |

## Reset plan

- CPU_RESETN (active low, async to the board) goes through `reset_sync` (the only asynchronous-assert element,
  a reset synchroniser). Its active-high output `rst` is the only reset inside the design.
- Reset clears: tick counter, count, debounce counter, scan slot counter, and the shell's control state (inside fpga_shell).
- Datapath registers (BCD working registers, seg/an output registers) have no reset; the output registers are
  written every cycle from the scan state, which is itself reset.

## Crossings

| From | To | Signal | Primitive | Inlined in |
|---|---|---|---|---|
| CPU_RESETN (async) | clk | rst | reset_sync | top |
| BTNC (async) | clk | btnc | sync2 | btn_debounce |
| UART_TXD_IN (async) | clk | uart line | sync2 | uart_rx (inside fpga_shell) |

No signal crosses clock domains other than these; there is one clock.

## Pin list (resource names; pin numbers are set by board_constraints from the master XDC)

| Top port | Board resource | Direction | Notes |
|---|---|---|---|
| CLK100MHZ | 100 MHz oscillator | in | clk |
| CPU_RESETN | CPU RESET button | in | active low |
| BTNC | centre button | in | active high |
| SEG[7:0] | CA CB CC CD CE CF CG DP | out | active low; bit 0 = CA ... bit 7 = DP |
| AN[7:0] | AN0 .. AN7 | out | active low; AN4..AN7 held high |
| UART_TXD_IN | USB-UART receive pin (host to FPGA) | in | to fpga_shell |
| UART_RXD_OUT | USB-UART transmit pin (FPGA to host) | out | from fpga_shell |

Outputs (SEG, AN, UART_RXD_OUT) are driven from registers.

## Resource prediction

| Resource | Predicted | Basis |
|---|---|---|
| lut | [120, 450] | counters (27+20+17+14 bit), BCD double dabble, segment decode, window mux, UART and shell |
| ff | [100, 350] | counters, BCD working and output registers, shell and UART state |
| bram_tile | 0 | no memory |
| dsp | 0 | no multiply |

## Library entries considered

`ip_lookup` was run twice in this stage (logged in build/ip_lookup.jsonl):

- Button debounce with clear pulse: `freq_duty_counter` was returned as a weak match. It counts edges and
  high clocks over a fixed gate; it does not hold a press for DEBOUNCE_CYCLES or emit a clear pulse. Not taken.
  The debouncer is written fresh (sync2 plus a consecutive-high counter), as in btn_debounce above.
- Seven-segment multiplexed scan with BCD conversion: nothing in the library fits. Not taken; seg_display is
  written fresh.

The UART and test shell are reused from `shell/rtl` (not a library entry).

## Open questions for the owner

1. Port names. The spec's port names are lowercase (clk, cpu_resetn, btnc, seg, an, uart_rxd, uart_txd). The flow
   convention is that top-level names are the master XDC's (CLK100MHZ, BTNC, UART_RXD_OUT), and the UART pair must
   be UART_TXD_IN and UART_RXD_OUT. This design uses the convention names. The owner should confirm this
   rename, since FDA-CON-8 checks the spec's ports against the top module.
2. The shell register addresses. The spec's offsets 0x00 and 0x04 are the design's window offsets; the shell
   exposes them at 0x80 and 0x84. The owner should confirm this mapping.
