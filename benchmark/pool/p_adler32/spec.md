# Adler-32 checksum

I want to checksum a stream of bytes sent from the PC with Adler-32, the one used in zlib.

- It keeps the two running sums and combines them into the 32-bit checksum. I should be able to send a byte at a time,
  or four bytes in one write to go faster; in a four-byte write the lowest byte goes first.
- I want to read the checksum, the sums, and how many bytes have gone in, and start over.
- LED[15:0] show the first (low) sum.
- All over the test shell (USB-UART, 115200 baud). The design ID is "ADLR".

Test hooks: top module `p_adler32_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
