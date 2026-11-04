# t2_spi_master_modes: reviewer notes

- **Twin:** the textbook's SPI master for the ADXL362 (mode 0 only, fixed byte sequence).
- **Trap:** `test_mode3_idle_high`: SCLK must idle high in mode 3, MOSI must change on falling edges and data is
  sampled on rising edges; the trap variant (CPOL/CPHA tied to 0) fails it (and the other non-zero-mode tests).
- **Left out of spec.md on purpose:** register offsets and bit positions, the 1 MHz reset value as DIV = 50, the
  setup/hold half periods around CS_N, what a TXDATA write does while busy (ignored), MOSI level when idle, how
  bits fill RXDATA for LSB-first and 8-bit frames, that DONE is sticky/W1C only, CS_ACTIVE in STATUS.
- **Review:** the bench checks SCLK edge spacing exactly (DIV clocks), but allows the first edge anywhere from DIV
  to 2*DIV after CS_N falls and CS_N to rise DIV to 2*DIV after the last edge, so a design that adds a clock of
  setup is not failed. Tests with an external slave use DIV >= 5 (the spec says MISO is synchronised; with DIV < 5 a
  slave that changes MISO on the opposite edge is not guaranteed); DIV = 2 and 3 are tested in loopback.
- Hardware: Pmod JB has nothing attached; selfcheck uses the loopback bit.
