# Bring-up: p5_async_fifo_soak

## Setup
- KR260 powered, JTAG connected, bitstream programmed (the owner approves programming).
- No UART; the host uses the JTAG register bus (BSCANE2 USER4, `jtag_bus`).
- No SFP+ module needed; `sfp_tx_disable` is driven to 1. The 156.25 MHz reader clock must come from the board's SFP reference clock source.

## Testing
1. Read 0x000: pass if it equals 0x20950001. Fail otherwise.
2. Read 0x004 (BUILD): pass if it is the non-zero USR_ACCESS stamp of this bitstream.
3. Write 0x008 a value, read it back: pass if equal; after reset it reads 0.
4. Write CTRL (0x010)=4 (CLEAR with RUN 0), write SNAPSHOT 0x030, read 0x014-0x02C: pass if all 0.
5. Write CTRL=1 (RUN) for ~50 ms, then CTRL=9 (INJECT), then CTRL=0 and wait: pass if CTRL bit 3 reads 0 afterwards.
6. Write SNAPSHOT, read counters: pass if WORDS_W>0, WORDS_R==WORDS_W, DATA_ERRS==1, OVERFLOWS==0, UNDERFLOWS==0, OCC_MAX<=512.
7. Write CTRL=4 and SNAPSHOT: pass if all counters read 0. LED0 = RUN, LED1 = error seen.

`python -m flow.bringup` runs these via hw_checks.py.

## Debug aids
- LED0 shows RUN, LED1 any error seen.
- SLOW_READ (CTRL bit 1) fills the FIFO: STALL_W then increments and OCC_MAX reaches 512.

## If it fails
- DATA_ERRS>1 or OVERFLOWS/UNDERFLOWS non-zero: check the clk_wr/clk_rd async clock groups and CDC max_delay constraints in the timing report.
- WORDS_R stays 0: the 156.25 MHz reference clock is missing.
- All reads 0: bitstream not loaded or JTAG chain wrong.

<!-- lab:begin (written by the harness; regenerated each run) -->

## Lab instruments

The lab file (`hil/lab.example.yaml` is the template) lists the instruments; this section is generated from it. You run every instrument step yourself, one at a time: `python -m hil.lab_bringup run <design>`. The agent has only dry-run it against mock instruments. A step marked DRIVES puts a signal into the board and asks you to type `yes` first.

No requirement of this design states a frequency or a level that an instrument could check, so there are no instrument steps.

<!-- lab:end -->
