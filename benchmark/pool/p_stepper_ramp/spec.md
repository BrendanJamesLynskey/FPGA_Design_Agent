# Stepper motor move generator

I want to drive a stepper-motor driver board that takes STEP and DIR inputs, on Pmod JA: JA1 is STEP, JA2 is DIR and
JA3 is the driver's enable, which is active low.

- I tell it how far to go as a signed number of steps over the test shell: positive is one direction, negative the
  other. Each step is one pulse on STEP.
- A real motor cannot start at full speed, so a move ramps: the first steps are slow, each interval a little shorter
  than the one before, until the top speed is reached, and at the end the intervals lengthen again so the motor stops
  gently. A short move never gets to top speed: it speeds up and slows down symmetrically.
- The driver is enabled just before the move and stays enabled for a short hold time afterwards. DIR is set a little
  before the first step and not changed during the move.
- The design keeps track of the position in steps.
- A move that arrives while another is running is refused and counted. A move of zero steps does nothing.
- LED[0] is lit while the driver is enabled, LED[1] follows STEP, LED[2] follows DIR. The design ID is "STEP".

Test hooks: top module `p_stepper_ramp_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `START_INT`, `MIN_INT` and `RAMP_DEC` (the slowest and
fastest step interval and the amount the interval changes per step, in clocks), `PULSE_CYCLES` (the STEP pulse width),
`DIR_SETUP` (clocks from enabling and setting DIR to the first step) and `HOLD_CYCLES` (clocks the driver stays enabled
after the last step pulse) as top-level parameters.
