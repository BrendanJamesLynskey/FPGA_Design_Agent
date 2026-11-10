# Gray-code stepper on the LEDs

I want a 10-bit Gray-code counter shown on LED[9:0] of the Nexys A7-100T.

- Each press of BTNU steps the counter once. SW[15] picks the direction: down when it is up (1), up when it is
  down (0). The button bounces, so one press must give exactly one step.
- There is also an automatic mode that steps on its own at a rate I set over the shell, in milliseconds per
  step; a rate of zero means it stands still. Buttons still work in automatic mode: a press gives one step of
  its own and does not disturb the automatic ones, which carry on exactly the set rate apart.
- The whole point is that exactly one LED changes on every step, including when the count wraps round at either
  end. I want that checked on every step of the whole count, in both directions, not just on a few.
- LED[15] is lit while automatic mode is on. The other LEDs stay off.
- CPU_RESETN resets everything.
- Over the test shell (USB-UART, 115200 baud) I can read the Gray code, read and set the count in plain binary,
  turn automatic mode on and off, set the rate, and read how many steps have been taken. The design ID is "GRAY".

Test hooks: top module `t1_gray_stepper_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `DEBOUNCE_CYCLES` (debounce time in clocks) and
`TICK_CYCLES` (clocks per unit of the rate, one millisecond on the board) as top-level parameters.
