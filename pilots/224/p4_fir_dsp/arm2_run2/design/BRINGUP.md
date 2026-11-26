# fir32_sym bring-up

## Setup

- Board: Kria KR260, programmed with the design's bitstream over JTAG (the owner approves programming).
- No UART and no ILA build. The host reads and writes registers through the JTAG register bus (BSCANE2 USER4, `jtag_bus`).
- The 25 MHz clock and the internal power-on reset (16 cycles) start the design; LED0 shows BUSY, LED1 is 0.
- Register map: 0x000 ID, 0x004 BUILD, 0x008 SCRATCH, 0x010 CTRL (bit0 CLEAR, bit1 RUN), 0x014 IN_PUSH,
  0x018 OUT_POP, 0x01C STATUS, 0x020 SAT_COUNT, 0x024 SAMPLES_DONE.

## Testing

Run `flow/bringup.py` for this design; it runs these steps (hw_checks.py):

1. Read 0x000. Pass: 0x20940001. Fail: any other value (wrong bitstream or bus).
2. Read 0x004. Pass: equals the build's USR_ACCESS word (non-zero for a flow build).
3. Write 0x008 with patterns, read back. Pass: identical value; resets to 0.
4. Write CTRL = 1 (CLEAR), read STATUS. Pass: 0x00000000.
5. Push 12 samples to 0x014; read STATUS. Pass: bits 15:4 = 12.
6. Write CTRL = 2 (RUN); poll STATUS until bit 0 = 0. Pass: finishes; bits 31:20 = 12.
7. Read OUT_POP 12 times. Pass: bit 31 = 1 and bits 15:0 equal the Python model's outputs, in order.
8. Read OUT_POP once more. Pass: 0.
9. Read SAMPLES_DONE (12) and SAT_COUNT (model value; the test vector includes full-scale samples).
10. Write CLEAR; SAMPLES_DONE, SAT_COUNT and STATUS read 0.

## Debug aids

- LED0 = BUSY: stuck on means RUN never completed (datapath clock or MMCM not locked).
- STATUS counts show whether pushes and results arrive; SAMPLES_DONE shows datapath progress.
- Write CLEAR (CTRL=1) to return to a known state.

## If it fails

- ID wrong or reads all ones/zeros: bitstream not loaded or the JTAG chain/USER4 not reached.
- Outputs wrong but counts right: coefficients (data/coeffs.hex) or pipeline; compare with model.py.
- BUSY never clears: MMCM unlocked or clk_dsp timing failure; check the post-route timing report.
- Counts wrong right after CLEAR: wait a few microseconds and read again (CLEAR crosses clock domains).
