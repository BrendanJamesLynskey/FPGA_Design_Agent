# Servo pulse generator

I want to drive a hobby servo from the switches.

- A servo wants a pulse on its signal wire once every frame. The pulse is 1 ms wide at one end of its travel and
  about 2 ms wide at the other, and the position in between follows the width. The signal is on Pmod JA pin 1.
- SW[7:0] set the position, 0 to 255. The position is picked up once at the start of each frame, so the pulse that is
  going out is never cut short or stretched by a switch moving halfway through it.
- SW[15] up switches the servo off: the signal stays low.
- LED[7:0] show the position being used, LED[15] shows that the servo is switched off.
- Over the test shell (USB-UART, 115200 baud) I can read the position in use and the pulse width in clocks. The design
  ID is "SRVO".

Test hooks: top module `p_servo_pwm_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `FRAME_CYCLES` (frame length in clocks),
`MIN_CYCLES` (pulse width at position 0) and `STEP_CYCLES` (extra width per position step) as top-level parameters.
