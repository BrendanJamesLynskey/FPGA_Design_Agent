# Bring-up: P1 clock frequency meter

## Setup
- Board: KR260 with the bitstream for `freq_meter_top` loaded over JTAG.
- The 25 MHz clock on pin C3 runs; the SFP+ quad MGTREFCLK0 must carry the 156.25 MHz reference. No SFP module is needed, the laser stays off (`sfp_tx_disable` = 1).
- Host reaches the registers over the JTAG USER4 register bus (`jtag_bus`); there is no UART.

## Testing
1. Read 0x000 (ID). Pass: 0x20910001.
2. Read 0x004 (BUILD). Pass: non-zero USR_ACCESS word that matches the bitstream build.
3. Write 0x008 with 0xA5A5A5A5, read back. Pass: same value; after reset it reads 0.
4. Read 0x010 (GATE_LEN). Pass: 156250000 decimal.
5. Write 0x010 = 156250 (1 ms), write 0x014 = 1 (START), poll 0x018 until bit 1 (DONE). Pass: DONE within 2 s, BUSY (bit 0) clear.
6. Read 0x020 (GATE_ACTUAL). Pass: 156250. Read 0x1C (COUNT). Pass: 25000 within 100 ppm (25000 +-3 edges at 1 ms).
7. Read 0x024 (MEAS_DONE) before and after step 5. Pass: it rises by exactly 1.
8. Write 0x010 = 10, START, wait for DONE. Pass: GATE_ACTUAL reads 1000 (clamp).
9. With the default 1 s gate, COUNT x 156.25 MHz / GATE_ACTUAL is 25 MHz within 100 ppm; five readings agree within 10 ppm.
10. Write 0x014 = 2 (LED_EN): led[0] blinks (C3, 1 Hz toggle) and led[1] (reference). Write 0 to turn both off.

## Debug aids
- STATUS (0x018): BUSY bit 0, DONE bit 1.
- SCRATCH (0x008) tests bus access independently of the clocks.
- LEDs show whether each clock is alive.

## If it fails
- ID or SCRATCH wrong: JTAG bus problem; check the bitstream is loaded and USER4 is used.
- DONE never sets: reference clock missing (check MGTREFCLK0 source); the register bus still answers since it runs on C3.
- COUNT off by more than 1 edge from expectation: check the C3 oscillator frequency.
- Restore reset values afterwards: GATE_LEN 156250000, CTRL 0, SCRATCH 0.
