# c14_int8_dot_requant architecture

Quantised-layer unit: acc = sum(act[i]*wgt[i]) + bias; y = clamp(round(acc*mult / 2^shift)), behind the UART test shell on the Nexys A7-100T.

## Block diagram

```text
 UART_TXD_IN --> [fpga_shell] --win_*--> [dotq_regs] --core_*--> [dotq_core]
 UART_RXD_OUT <-- [fpga_shell] <--rdata-- [dotq_regs] <--y,acc,done-- [dotq_core]
 CPU_RESETN --> [reset_sync] --rst--> all blocks
 dotq_regs.ready --> LED0
```

- dotq_regs: operand registers (A_LO..CTRL), GO write makes a one-cycle `go` pulse, clears READY; on `done` latches y/acc and sets READY. Y/ACC read 0 while READY=0.
- dotq_core: stage 1 eight 8x8 products; stage 2 adder tree + bias (32-bit acc); stage 3 acc*mult (48/49-bit signed); stage 4 add rounding constant 2^(shift-1) and arithmetic shift; stage 5 clamp (relu aware); done asserted within 8 clocks of go.

## Clock plan

Single domain CLK100MHZ, 100 MHz (10 ns), no MMCM/PLL. Synchronous reset: CPU_RESETN (active low, async button) goes through a 2-flop reset_sync to an active-high sync reset, applied within 2 cycles. UART_TXD_IN is synchronised inside the shell. CLKS_PER_BIT = 868, TIMEOUT_CYCLES = 100000000, BUILD_STAMP top parameter default 0.

## Pin list

| Port | Dir | Pin | Role |
|---|---|---|---|
| CLK100MHZ | in | E3 | 100 MHz clock |
| CPU_RESETN | in | C12 | reset, active low |
| UART_TXD_IN | in | C4 | host to FPGA serial |
| UART_RXD_OUT | out | D4 | FPGA to host serial |
| LED[0] | out | H17 | READY flag (LED declared as a bus; only bit 0 used) |

Pins and I/O standards come from the master XDC through board_constraints; I/O delay lines are appended in design.xdc.

## Resource prediction

LUT 300-1400, FF 350-1300, BRAM 0, DSP 0-12 (8 products plus the acc*mult multiplier may map to DSP48 or fabric).
