# fir_lowpass32: architecture

32-tap low-pass FIR filter on the Nexys A7-100T, Q1.15 signed coefficients, 16-bit signed samples, driven and
read over the USB-UART test shell (`fpga_shell`). Single clock domain at 100 MHz. One DSP48E1, no block RAM.

## Block diagram

```text
                    host PC (USB-UART, 115200 8N1)
                          |             ^
                 UART_TXD_IN |          | UART_RXD_OUT
                 (C4)     v             |  (D4)
   +--------------------------------------------------------------+
   | fir_top                                                      |
   |                                                              |
   |  CPU_RESETN --> reset_sync --> rst (active high, inside)     |
   |                                   |                          |
   |  +---------------------------------v------------------------+ |
   |  | fpga_shell : uart rx/tx, request parser, window 0x80-FF  | |
   |  +--------------------------+-------------------------------+ |
   |                             | win_addr, win_wr, win_rd,      |
   |                             | win_wdata, win_rdata           |
   |  +--------------------------v-------------------------------+ |
   |  | fir_regs : ID, SAMPLE_IN, RESULT, STATUS, COEF_ADDR,    | |
   |  |            COEF_DATA decode                             | |
   |  +------+---------------------+----------------------+-----+ |
   |         | sample (write)      | coef (addr, data)    | run   |
   |  +------v--------------+ +----v-----------------+ +--v-----+ |
   |  | fir_delay_line      | | fir_coef_bank        | | fir_mac| |
   |  | 32 x 16 FF shift    | | 32 x 16 FF + 32:1 mux| | seq +  | |
   |  |  x[n-k], k = 0..31  | |  c[k], k = 0..31     | | DSP48E1| |
   |  +----------+----------+ +----------+-----------+ +---+----+ |
   |             +------- x[n-k] and c[k] --------------->|      |
   |                                                       v      |
   |                       RESULT (sat(acc >>> 15)), busy, valid  |
   +--------------------------------------------------------------+
```

## Blocks

| Block | Function |
|---|---|
| `fir_top` | Board top. Instantiates `fpga_shell` and `reset_sync`. Inverts the synchronised reset once (`rst = ~cpu_resetn` after the synchroniser) and passes `rst` to every block. |
| `fpga_shell` | Shared test shell (`shell/rtl/fpga_shell.sv`). Protocol per `shell/PROTOCOL.md`. Registers 0x80-0xFF are the design window. `DESIGN_ID` = `32'h46494C54` ("FILT"). |
| `fir_regs` | Window decode. Window word n maps to spec byte offset 4n: word 0 ID, 1 SAMPLE_IN, 2 RESULT, 3 STATUS, 4 COEF_ADDR, 5 COEF_DATA. |
| `fir_delay_line` | 32 x 16-bit signed shift register of flip-flops, newest sample at index 0. Shifts on each accepted SAMPLE_IN write (not while busy). |
| `fir_coef_bank` | 32 x 16-bit signed coefficient registers of flip-flops. COEF_DATA write stores at COEF_ADDR. Read through a 32:1 mux. Reset to zero. |
| `fir_mac` | Run sequencer and one DSP48E1 used as a multiply-accumulate, one tap per clk over 32 taps. Accumulator arithmetically shifted right by 15 and saturated to the signed 16-bit range. Holds `busy` (STATUS bit 0) and `result_valid` (STATUS bit 1). |

## Address map

Shell address = window word + 0x80. Spec byte offsets are word-scaled inside the window.

| Shell ADDR | Spec offset | Name | Access | Reset |
|---|---|---|---|---|
| 0x80 | 0x00 | ID | RO | 0x46494C54 |
| 0x81 | 0x04 | SAMPLE_IN | WO | 0 |
| 0x82 | 0x08 | RESULT | RO | 0 |
| 0x83 | 0x0C | STATUS (bit 0 busy, bit 1 result_valid) | RO | 0 |
| 0x84 | 0x10 | COEF_ADDR (bits 4:0) | RW | 0 |
| 0x85 | 0x14 | COEF_DATA (bits 15:0) | RW | 0 |

Host framing is the shell's 8-byte request and 7-byte response (`shell/PROTOCOL.md`). It replaces the
provisional "W/R" framing in the clarify notes.

## Behaviour and timing

- SAMPLE_IN write while not busy: shift the delay line, start one run. Write while busy is ignored.
- A run takes 32 tap cycles plus pipeline (TAPS + 3 = 35 clk cycles from write to STATUS bit 1 set).
- Coefficient writes apply from the next run. A run never mixes old and new coefficients.
- `cpu_resetn` low clears the delay line, all coefficients, RESULT, COEF_ADDR and STATUS. ID is not reset.
- Reset is synchronous inside the design. The asynchronous button is handled once in `reset_sync`.

## Clock plan

| Domain | Clock port | Frequency | Source | Notes |
|---|---|---|---|---|
| clk | CLK100MHZ | 100 MHz (10 ns) | board oscillator, board resource CLK100MHZ | single clock domain; no MMCM or PLL |

Asynchronous inputs and their synchronisers (both are CDC primitives, listed in `architecture.yaml`):

| Signal | Synchroniser | Where |
|---|---|---|
| CPU_RESETN (async, active low) | `reset_sync`: asserts asynchronously, releases on two clk edges | `fir_top` |
| UART_TXD_IN (async) | `sync2` (two flops, ASYNC_REG) | inside `uart_rx` in the shell |

No other clock-domain crossings exist. The design has one clock.

## Reset plan

- Source: CPU RESET pushbutton, active low, asynchronous to clk.
- `reset_sync` gives one active-high synchronous reset `rst` for all control registers.
- Datapath registers (delay line, coefficient bank, DSP pipeline) take a synchronous reset only where the spec
  requires it: the delay line and coefficient bank are cleared by `rst`; DSP internal registers take no reset.

## Pin list

Board resource names come from the master XDC through `board_constraints`. The top-level port names follow
the master XDC (FDA-CON-7). The spec's names map as: clk = CLK100MHZ, cpu_resetn = CPU_RESETN,
uart_rx = UART_TXD_IN, uart_tx = UART_RXD_OUT.

| Top port | Direction | Board resource | Pin (spec.yaml) | I/O standard | Role |
|---|---|---|---|---|---|
| CLK100MHZ | in | CLK100MHZ | E3 | LVCMOS33 | 100 MHz clock |
| CPU_RESETN | in | CPU_RESETN | C12 | LVCMOS33 | CPU RESET, active low |
| UART_TXD_IN | in | UART_TXD_IN | C4 | LVCMOS33 | USB-UART RX, data from host |
| UART_RXD_OUT | out | UART_RXD_OUT | D4 | LVCMOS33 | USB-UART TX, data to host |

The UART pair (`UART_TXD_IN`, `UART_RXD_OUT`) is declared together and both are constrained (FDA-CON-9).

## Predicted resources

| Resource | Predicted | Basis |
|---|---|---|
| LUT | 200 to 800 | 32:1 mux x16 for delay-line taps, 32:1 mux x16 for coefficient read, decode, run control, shell. Spec estimate is under 400 for the filter alone. |
| FF | 900 to 1500 | 512 delay-line + 512 coefficient flops + RESULT, control, shell. Spec estimate of about 700 undercounts the coefficient flops. |
| BRAM tile | 0 | No block RAM (spec assumption). |
| DSP48E1 | 1 | One time-multiplexed MAC (REQ-10). |
