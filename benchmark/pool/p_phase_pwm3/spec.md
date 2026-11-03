# Three staggered PWM channels

I want three PWM outputs on LED[0], LED[1] and LED[2] that share one duty setting but do not switch together,
the way a three-phase motor driver spreads its load.

- SW[7:0] set the duty, 0 to 255: 0 is always off, and the on-time grows with the number, though even 255 leaves a gap
  so the output is never solid on. The duty is picked up once per period, so changing the switches never makes a
  runt pulse.
- With SW[8] up the three channels are spread evenly across the period, each one-third of a period after the previous
  channel. With SW[8] down they all switch together.
- The period is a fixed number of clocks (a multiple of three).
- Over the test shell (USB-UART, 115200 baud) I can read the duty in use, the on-time in clocks and whether the
  channels are staggered. The design ID is "PH3P".

Test hooks: top module `p_phase_pwm3_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `PWM_PERIOD` (clocks in one PWM period) as a
top-level parameter.
