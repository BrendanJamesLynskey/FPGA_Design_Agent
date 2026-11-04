# I2C bus scanner on the temperature-sensor bus

I'd like a small I2C bus scanner on the Nexys A7-100T's sensor bus (TMP_SCL / TMP_SDA), like the "i2cdetect"
tool, so I can see what answers.

- When I tell it to start, it probes every normal 7-bit address from 0x08 to 0x77 in turn: a write-address probe,
  check for the ACK, then a STOP, and on to the next. The reserved addresses at both ends are left alone, and it
  must never send a data byte to anything.
- Results: a 128-bit map with one bit per address, how many answered, the lowest address that answered, and busy /
  done flags. A new scan starts from a clean map.
- The LEDs show how many devices answered.
- Open-drain lines with the board's pull-ups (never drive them high); a slave may stretch the clock.
- SCL speed from a parameter giving a quarter of the SCL period in clocks; 100 kHz on the board.
- Through the test shell; design ID "SCAN".

Test hooks: top module `t2_i2c_scanner_top`, ports named as in the board's master XDC (`TMP_SCL`, `TMP_SDA`, `LED`,
the USB-UART pins, `CLK100MHZ`, `CPU_RESETN`), the test shell's `CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP`
parameters, plus `QUARTER` (a quarter of the SCL period, in clocks) as top-level parameters.
