# low_pass_fir architecture (nexys_a7_100t, xc7a100tcsg324-1)

A 32-tap low-pass FIR with run-time Q1.15 coefficients. The host loads coefficients and samples over the
UART test shell (115200 8N1). One shared DSP48E1 performs the 32 multiply-accumulates of each sample pass.

## Block diagram

```text
 host (USB-UART)
     |  uart_rx (UART_TXD_IN, C4)     uart_tx (UART_RXD_OUT, D4)
     v                                 ^
 +---------------------------- filt_top ------------------------------------+
 |                                                                         |
 |  cpu_resetn (CPU_RESETN, C12) -> reset_sync -> rst (active high, clk)   |
 |                                                                         |
 |  +-------------- fpga_shell (provided) ---------+                       |
 |  | uart_rx -> frame decoder -> uart_tx          |                       |
 |  +------------------+---------------------------+                       |
 |                     | win_addr[6:0] win_wr win_rd win_wdata win_rdata   |
 |                     v                                                   |
 |  +----------------- fir_regs ---------------------------------------+    |
 |  | ID, SAMPLE_IN, SAMPLE_OUT, STATUS.busy, COEF_0..31 (32x16 RW)    |    |
 |  | sample history 32x16 (shift, new sample at tap 0), busy counter  |    |
 |  +------------------+----------------------------------------------+    |
 |                     | mac_coef, mac_hist, mac_k, mac_start             |
 |                     v                                                   |
 |  +----------------- fir_mac ----------------+                           |
 |  | one DSP48E1: P = P + COEF_k * hist_k      |  -> sum >>> 15, sat16     |
 |  +-------------------------------------------+       -> SAMPLE_OUT    |
 +-------------------------------------------------------------------------+
```

## Clock plan

| Domain | Clock port | Source | Frequency | Notes |
|---|---|---|---|---|
| clk | `clk` (board `CLK100MHZ`, pin E3) | board oscillator | 100 MHz | the only clock; no MMCM/PLL; every register is on clk |

The only asynchronous inputs are the CPU reset button and `uart_rx`. `uart_rx` is synchronised inside the
shell's receiver by `sync2`. The CPU reset is synchronised by `reset_sync`.

## Reset plan

- `cpu_resetn` (board `CPU_RESETN`, pin C12, active low) enters the design once, in `reset_sync`: a
  two-flop synchroniser on clk. Its output is inverted once to give `rst`, active high.
- Inside the design there is one reset, `rst`, active high, synchronous (no reset in any sensitivity
  list outside `reset_sync`). No other polarity is used.
- Reset is applied only where the spec requires it: busy and the sequencer, SAMPLE_OUT, the 32 COEF_k
  registers and the 32 history entries (REQ-02, 03, 04, 22, 23). The DSP48E1 is used without a reset
  pin driven by logic; its accumulator is cleared by the sequencer's first-tap OPMODE selection, so no
  asynchronous or logic-driven reset reaches the DSP.
- The shell's `rst` input is the same `rst`.

## Pin list (board resource -> top port)

| Board resource | Pin | Top port | Direction | Standard |
|---|---|---|---|---|
| CLK100MHZ | E3 | clk | in | LVCMOS33 (board clock constraint, 10 ns) |
| CPU_RESETN | C12 | cpu_resetn | in | LVCMOS33 |
| UART_TXD_IN | C4 | uart_rx | in | LVCMOS33 |
| UART_RXD_OUT | D4 | uart_tx | out | LVCMOS33 |

Only these four ports exist on the top. The UART is a pair (both directions constrained, FDA-CON-9).
Pin locations and I/O standards are written by `board_constraints`, not by hand. The I/O timing lines
(input delay on `cpu_resetn`/`uart_rx`, output delay on `uart_tx`, half a period) are appended in `design.xdc`.

## Register map (host view)

The spec's byte offsets are in design space. The shell's registers are word-numbered (0x00-0x05), so each
design register is at window address `0x80 + offset/4` (shell ADDR), i.e. `win_addr = offset/4`:

| Spec offset | Name | Shell ADDR | win_addr | Access | Reset |
|---|---|---|---|---|---|
| 0x00 | ID | 0x80 | 0 | RO | 0x46494C54 ("FILT") |
| 0x04 | SAMPLE_IN | 0x81 | 1 | WO | 0x0000 |
| 0x08 | SAMPLE_OUT | 0x82 | 2 | RO | 0x0000 |
| 0x0C | STATUS | 0x83 | 3 | RO | 0x00000000 (bit 0 busy) |
| 0x10+4k | COEF_k, k=0..31 | 0x84+k | 4+k | RW | 0x0000 |

Window addresses 0..35 are used. The shell's `DESIGN_ID` parameter is set to "FILT" (0x46494C54).
The shell's framing and data packing are to be confirmed against `@shell/PROTOCOL.md` before RTL.

## Datapath and timing

- An accepted SAMPLE_IN write (busy = 0) shifts the 16-bit sample into the history at tap 0 and sets busy
  for exactly 34 clk cycles: 32 MAC cycles (k = 0..31) plus two pipeline cycles.
- During busy, fir_mac computes sum_k COEF_k * hist_k with one DSP48E1, one term per clk. The product is
  Q2.30; the 48-bit sum is shifted right arithmetically by 15 (truncation toward minus infinity, no
  rounding offset) and saturated to signed 16 bits (0x7FFF / 0x8000) into SAMPLE_OUT.
- Writes to SAMPLE_IN or COEF_k while busy = 1 are ignored (no shadow storage).
- The worst-case sum is 32 * 2^30 = 2^35, which needs 36 bits; the 48-bit accumulator leaves margin.

## Resource prediction

| Resource | Predicted | Basis |
|---|---|---|
| DSP48E1 | 1 | one shared MAC (REQ-15) |
| BRAM36 | 0 | coefficients and history are flip-flops (32x16 each) |
| FF | 1000-1600 | 512 coefficient bits + 512 history bits + UART/shell (~150) + control and DSP pipeline. The spec's "about 400 FF" estimate is too low for the 1024 storage bits. |
| LUT | 300-800 | 32:1 x 16 read-back mux for COEF_k (~180), 32:1 x 16 coefficient and history selection into the DSP (~350), shell and UART logic, saturation |

The same numbers are in `architecture.yaml` (`predicted_resources`).

## Library entries considered

- `fir` (ip_lib, query "32-tap FIR filter with run-time coefficients, single DSP multiply-accumulate"):
  **not taken**. Its `serial` variant (1 DSP, 181 LUT, 269 FF, II 19, latency 24) is the closest fit on
  resources, but its contract is valid/ready streams with full-precision output: it has no register-map
  access, no 34-cycle busy window (it needs II 19 per sample and a 24-clock latency), no arithmetic shift
  by FRAC_BITS and no 16-bit saturation (REQ-07, REQ-09, REQ-10, REQ-12, REQ-13). Wrapping it would need
  the same sequencer and output stage as a fresh design, so the block is written fresh in `fir_regs` and
  `fir_mac`.

## Open items for the owner

- Approve ARCHITECTURE.md and architecture.yaml before any RTL is written (they are frozen after approval).
- The RTL under `rtl/` does not exist yet, so `check_constraints` reports the rtl sources entry as unmatched;
  this clears when the RTL stage writes `rtl/*.sv`.
