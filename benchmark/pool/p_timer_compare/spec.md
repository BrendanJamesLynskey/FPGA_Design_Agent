# Timer with output compare

I want a general-purpose timer I can configure over the shell, in the style of a microcontroller timer block.

- A 32-bit counter counts up, one count per prescaler period. I set the prescaler, and start and stop the timer.
- Two compare values, A and B. When the counter reaches a compare value that is a match: it sets a flag that stays
  until I clear it, and the channel's output pin acts on it. Each channel is set up to do nothing, to go high, to go
  low or to toggle on a match. The outputs are LED[0] for channel A and LED[1] for channel B.
- The counter can be told to start again from zero after it has reached compare A, which makes a repeating timer.
- Writing the control register also forces both outputs to a chosen start level.
- The design ID is "TMRC".

Test hooks: top module `p_timer_compare_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
