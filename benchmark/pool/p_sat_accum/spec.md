# Saturating accumulator

I want a running total that follows the switches and stops at its limits instead of wrapping round.

- SW[7:0] hold a signed number (two's complement, so 0xFF is -1). At a steady rate the design adds that number to a
  16-bit signed running total.
- The total must never wrap: once it reaches its high or low limit it stays there. Two flags remember whether the
  total has ever been held back at the top or at the bottom.
- SW[15] up freezes the total (no adds). SW[14] up forces the total to zero while it is up, and wins over the freeze.
- LED[15:0] show the total as a 16-bit two's-complement number.
- I want to read the total, the flags and how many adds have happened, set the total, and clear the flags and the add
  count, over the test shell (USB-UART, 115200 baud). The design ID is "SATA".

Test hooks: top module `p_sat_accum_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `ACC_PERIOD` (clocks between adds) and `SAT_LIMIT`
(the limit magnitude) as top-level parameters.
