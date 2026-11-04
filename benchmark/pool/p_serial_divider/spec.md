# Sequential divider

I want a small unsigned divider that I drive from the PC, and I care how long it takes.

- It divides a 16-bit number by a 16-bit number and gives a quotient and a remainder. It works one bit per clock, like
  long division, rather than using the DSP slices.
- Some cases are quick: when the divisor is bigger than the dividend there is nothing to do, and a divisor of
  zero must not hang the design. Dividing by zero gives an all-ones quotient, the dividend as remainder, and a flag.
- I want to read back exactly how many clocks the last division took.
- LED[7:0] show the low byte of the quotient and LED[15] shows the divide-by-zero flag.
- It is all done over the test shell (USB-UART, 115200 baud). The design ID is "SDIV".

Test hooks: top module `p_serial_divider_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
