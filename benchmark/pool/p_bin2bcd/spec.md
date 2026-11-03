# Binary to decimal converter

I want to type a number over the test shell and see it as decimal on the display, as a converter I can reuse later.

- The number I send is a magnitude of up to 17 bits plus a separate sign bit (sign and magnitude, not two's
  complement). A negative zero is just zero.
- The converter gives the magnitude as five decimal digits in BCD. The largest it can show is 99999: anything bigger
  is clamped to 99999 and an overflow flag is raised.
- The seven-segment display shows the magnitude in decimal on the right, without leading zeros (zero shows as a
  single 0). A minus sign appears just to the left of the first digit when the number is negative. On overflow an E
  is also lit, in the seventh digit from the right.
- LED[15:0] show the low 16 bits of the BCD result.
- Over the test shell (USB-UART, 115200 baud) I can write the number and read back the BCD, sign and overflow. The
  design ID is "B2BD".

Test hooks: top module `p_bin2bcd_top`, ports named as in the board's master XDC, the test shell's `CLKS_PER_BIT`,
`TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `REFRESH_BITS` (each display digit is lit for 2^REFRESH_BITS
clocks) as a top-level parameter.
