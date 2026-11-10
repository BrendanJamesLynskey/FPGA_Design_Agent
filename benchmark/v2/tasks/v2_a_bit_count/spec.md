# Bit counter

I want a block on the Nexys A7-100T that takes a 32-bit word and tells me three things about its bits.

- How many bits are 1.
- How many zeros there are before the first 1, starting from the top (bit 31) and counting down.
- The word with its bits in the opposite order (bit 0 swapped with bit 31, and so on).
- The number of 1 bits is also shown in binary on LED[5:0]; the other LEDs stay off.
- CPU_RESETN resets everything to zero.
- Over the test shell (USB-UART, 115200 baud) I can set the word and read the three answers. The design ID is
  "BCNT".

Test hooks: top module `v2_a_bit_count_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
