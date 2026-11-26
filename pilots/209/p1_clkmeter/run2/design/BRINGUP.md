# Bring-up: p1_freq_meter

Measures the 25 MHz clock on pin C3 against the 156.25 MHz SFP GT reference clock. Host access is JTAG only (no UART).

## Setup
1. Connect the KR260 with its JTAG/USB cable; the SFP+ cage needs no module (laser off, `sfp_tx_disable`=1).
2. Program `build/base/freq_meter_top.bit` (after owner approval).
3. Run the bring-up over the JTAG register bus (USER4). The ref clock must be running for the bus to respond.

## Testing
1. Read 0x000 (ID). Pass: 0x20910001. Fail: anything else.
2. Read 0x004 (BUILD). Pass: equals the build record's USR_ACCESS word.
3. Write 0x008 SCRATCH with 0xA5A5A5A5, read back. Pass: same value; after reset it reads 0.
4. Read GATE_LEN 0x010 and CTRL 0x014. Pass: 156250000 and 0 (LED_EN off, START reads 0).
5. Write GATE_LEN=1562500 (10 ms), CTRL=1, poll STATUS 0x018. Pass: DONE (bit1) set, BUSY clear.
6. Read GATE_ACTUAL 0x020. Pass: exactly 1562500.
7. Read COUNT 0x01C. Pass: 250000 within 100 ppm (+-25; +-1 edge CDC uncertainty).
8. MEAS_DONE 0x024 increased by 1 per measurement. Pass: +1.
9. Write GATE_LEN=10, start. Pass: GATE_ACTUAL = 1000.
10. Write CTRL=2 (LED_EN): led[0] and led[1] blink at about 1 Hz; CTRL=0 turns both off. Restore GATE_LEN=156250000.

## Debug aids
- STATUS BUSY/DONE show gate progress; COUNT = 0 with DONE=1 means no C3 clock.
- LEDs blink independently from each clock (led[0] c3, led[1] ref).
- `build/base/timing_summary.rpt` for the clock-domain timing.

## If it fails
- No response on the bus: ref clock absent (check the SFP refclk source) or wrong bitstream.
- COUNT off by more than 1 edge or 100 ppm: check the 25 MHz source on C3.
- GATE_ACTUAL differs from GATE_LEN: gate logic fault; report the register dump.
