# Temperature alarm with the on-board ADT7420

Using the Nexys A7-100T's ADT7420 temperature sensor (I2C on TMP_SCL / TMP_SDA, address 0x4B), I want a
temperature monitor with a hardware alarm.

- On a configure command, set the sensor to its high-resolution 16-bit mode with the interrupt pin in comparator
  mode, active low, and load its high and low limits from two registers I write beforehand (raw sensor format).
- After that, read the temperature regularly (a parameter gives the period in clocks) and keep the raw 16-bit
  reading, the highest and lowest readings since configuring, and a count of readings.
- The alarm is the sensor's own TMP_INT pin: show it in a status bit and on LED0.
- Report I2C failures (no acknowledge) in the status.
- The usual open-drain care on the bus; the sensor may stretch the clock. SCL speed from a parameter giving a
  quarter of the SCL period in clocks (100 kHz on the board).
- Through the test shell; design ID "TALM".

Test hooks: top module `t2_adt7420_alarm_top`, ports named as in the board's master XDC (`TMP_SCL`, `TMP_SDA`,
`TMP_INT`, `LED`, the USB-UART pins, `CLK100MHZ`, `CPU_RESETN`), the test shell's `CLKS_PER_BIT`,
`TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `QUARTER` (a quarter of the SCL period, in clocks) and
`PERIOD_CYCLES` (clocks between temperature readings) as top-level parameters.
