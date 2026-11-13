# T1 LED dimmer and push-button counter — implementation plan

## Device and clock plan

- Board: Digilent Nexys A7-100T, FPGA part `xc7a100tcsg324-1`.
- One clock domain: the 100 MHz board oscillator on `clk` (E3), with a 10.00 ns period. Debounce, PWM, display scan, register logic, and the test shell use this clock; timing intervals are implemented as clock enables, never as derived clocks.
- `cpu_reset_n` is the active-low CPU reset input (C12). Assert asynchronously and release synchronously in the `clk` domain; connect the shell's synchronous active-high reset to the resulting internal reset.
- UART uses 868 clock cycles per bit (about 115207 baud) and the shell's 100000-cycle frame timeout.
- Default timing values: 1000000 cycles for button debounce, 256 phase counts for PWM, and 100000 cycles per display digit.

## Block diagram

```text
 Nexys A7-100T
 ┌─────────────────────────┐
 │ clk100 (100 MHz)         │──────┬──────────────┬───────────────────────┐
 │ CPU_RESETN (active low)  │──┐   │              │                       │
 │ BTNU / BTND / BTNC       │──┼───┼──> sync +    │                       │
 │ SW[7:0]                  │──┼───┼──> debounce  │                       │
 │ USB-UART RX/TX           │──┼───┼──> fpga_shell│                       │
 │                          │  │   │       │       │                       │
 │ LEDs[15:0] <─────────────┼──┼───┼───────┼──> counter + PWM            │
 │ AN[7:0], CA..CG, DP <────┼──┼───┼───────┼──> display scan/hex encoder  │
 └─────────────────────────┘  │   │       │       │                       │
                              └──> reset sync    └──> UART register window │
                                      │                    │              │
                                      └────── clk/rst ─────┴──────────────┘
```

## Register window and behavior partition

The test shell owns the UART framing and exposes the design window with byte offsets `0x00` through `0x20` (host addresses `0x80` through `0xA0`). The design-side register read value is registered for the cycle after `win_rd`. Register offsets are DESIGN_ID `0x00`, COUNTER `0x04`, BRIGHTNESS `0x08`, CONTROL `0x0C`, BUTTON_STATE `0x10`, SWITCH_STATE `0x14`, UP/DOWN/CENTRE_PRESS_COUNT `0x18`/`0x1C`/`0x20`.

Synchronize and debounce the three asynchronous buttons, then create one event on each debounced rising edge. The counter wraps modulo 65536; centre clear has priority, and simultaneous up/down events cancel. Switches are sampled for UART visibility and switch-selected brightness. The active brightness gates the counter-driven LEDs using linear 8-bit PWM with brightness 0 off and 255 continuously on. Scan eight active-low digits: AN3..AN0 show the counter MS-nibble first, AN7..AN6 show active brightness, AN5..AN4 are blank, and the display-disable control blanks all digits.

## Pin list

| Port | Direction | Nexys A7 resource | Pin(s) / role |
|---|---|---|---|
| `clk` | input | `clk100` | E3, 100 MHz oscillator |
| `cpu_reset_n` | input | `cpu_resetn` | C12, active-low CPU reset |
| `button_up` | input | `btnu` | M18, active high |
| `button_down` | input | `btnd` | P18, active high |
| `button_center` | input | `btnc` | N17, active high |
| `switches[7:0]` | input | `sw[0:7]` | SW0..SW7, J15/L16/M13/R15/R17/T18/U18/R13 |
| `uart_rx` | input | `uart_rxd_out` | D4, host-to-FPGA serial data |
| `uart_tx` | output | `uart_txd_in` | C4, FPGA-to-host serial data |
| `leds[15:0]` | output | `led[0:15]` | H17/K15/J13/N14/R18/V17/U17/U16/V16/T15/U14/T16/V15/V14/V12/V11, active high |
| `segments_n[7:0]` | output | `seg[0:7]` | CA..CG and DP, active low |
| `digit_enable_n[7:0]` | output | `an[0:7]` | AN0..AN7, active low |

All assigned user I/O uses the board master XDC's LVCMOS33 standard. `design.xdc` is generated from board resources; do not hand-edit package pins.