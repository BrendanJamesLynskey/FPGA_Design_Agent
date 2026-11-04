# Time-of-day clock

I want a wall clock on the seven-segment display.

- It shows hours, minutes and seconds in the six right-hand digits and keeps counting once a second. The two
  left-hand digits stay dark.
- SW[0] chooses 24-hour (down) or 12-hour (up) display. In 12-hour mode the hours run 1 to 12, midnight and noon
  both showing 12, an hour below ten has a blank tens digit, and LED[0] lights in the afternoon.
- The decimal points are used as the separators between hours, minutes and seconds.
- SW[1] up pauses the clock, with the second in progress held where it is.
- I can set the time, and read it back together with the number of midnights passed, over the test shell (USB-UART,
  115200 baud). The design ID is "TCLK".

Test hooks: top module `p_digital_clock_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `TICK_CYCLES` (clocks in one second) and
`REFRESH_BITS` (each display digit is lit for 2^REFRESH_BITS clocks) as top-level parameters.
