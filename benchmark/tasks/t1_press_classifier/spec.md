# Short and long press classifier

I want the centre button of the Nexys A7-100T to tell short presses from long ones.

- BTNC bounces, so debounce it first. When the button is let go, the press is classed as LONG if it was held for
  at least the long-press time (half a second on the board), otherwise SHORT. Nothing is decided while it is
  still held.
- Keep a count of short presses and a count of long presses, and remember how long the last press lasted, in
  milliseconds.
- LED[0] changes state on every short press and LED[1] on every long press, so I can see each one land.
  LED[15:8] show the low byte of the short-press count. The other LEDs stay off.
- CPU_RESETN resets everything.
- Over the test shell (USB-UART, 115200 baud) I can read both counts (writing either one clears it), the last
  press's length and whether it was long, and a status word (the debounced button level and the two LED states).
  The design ID is "PRSC".

Test hooks: top module `t1_press_classifier_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `DEBOUNCE_CYCLES` (debounce time in clocks),
`LONG_CYCLES` (the long-press threshold in clocks) and `TICK_CYCLES` (clocks per unit of the press length, one
millisecond on the board) as top-level parameters.
