# Shifter and rotator

I want a 32-bit shifter on the Nexys A7-100T that I can drive from the test shell.

- It has four operations: shift left, shift right, shift right keeping the sign, and rotate left. I choose the
  operation and the shift amount, and the result is shown live; the low 16 bits of the result are on LED[15:0].
- The amount is a number from 0 to 63.
- CPU_RESETN resets everything to zero.
- Over the test shell (USB-UART, 115200 baud) I can read and set the operand, read and set the operation and the
  amount, and read the full 32-bit result. The design ID is "SHFT".

Test hooks: top module `v2_a_shifter_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
