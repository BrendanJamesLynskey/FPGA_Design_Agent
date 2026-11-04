# Accelerometer activity monitor

I want to use the board's ADXL362 accelerometer as a wake-on-motion sensor: set it up to raise its interrupt line
INT1 when it detects activity, and then react to that interrupt.

- After reset the design waits a power-up delay, soft-resets the sensor, waits again, and then configures it over SPI
  (mode 0): the activity threshold and time, absolute-mode activity detection switched on, the activity event routed
  to INT1, and finally measurement mode on. Measurement mode must be the last thing written.
- While it is waiting the design watches INT1 (high means activity). When the line goes high it reads the sensor's
  status register, which also makes the sensor drop INT1, and then the X-axis data, and remembers them.
- The threshold and time come from registers on the test shell (USB-UART, 115200 baud) with defaults, and a command
  makes the design run the whole set-up again with the new values.
- LED[1] is lit once the sensor is configured and monitoring, LED[0] follows INT1, LED[15:8] show the top eight bits of
  the last X reading.
- Over the test shell I can also read how many activity events there have been, the status byte and the X value of the
  last one, and where the start-up sequence has got to. The design ID is "AACT".

Test hooks: top module `p_adxl362_activity_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `INIT_DELAY` (clocks after reset before the first
SPI transfer), `RESET_WAIT` (clocks after the soft reset before configuring) and `SCLK_HALF` (clocks in half an SCLK
period) as top-level parameters.
