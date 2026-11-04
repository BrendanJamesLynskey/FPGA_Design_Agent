# Rate multiplier

I want a tick generator whose rate is a fraction of the clock, the way a numerically controlled pulse source works.

- I set two numbers, N and M. While SW[0] is up the generator puts out exactly N one-clock ticks in every M clocks,
  spread as evenly as whole clocks allow, on LED[0].
- Two cases need a sensible rule: N larger than M gives a tick on every clock, and M of zero is treated as one.
- LED[1] flips every time a tick is sent.
- While SW[0] is down nothing happens and the generator holds its place.
- Over the test shell (USB-UART, 115200 baud) I can set N and M, read how many ticks have been sent, and reset the
  count and the generator's phase. The design ID is "RMUL".

Test hooks: top module `p_rate_mult_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
