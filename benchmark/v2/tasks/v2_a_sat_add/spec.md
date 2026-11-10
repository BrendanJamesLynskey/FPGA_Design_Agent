# Saturating adder

I want a 16-bit adder on the Nexys A7-100T that can saturate instead of wrapping round, and tells me when it ran
out of room.

- I give it two 16-bit numbers. A switch-like setting chooses whether they are treated as signed or unsigned, and
  another chooses whether the sum saturates (stops at the largest or smallest value that fits) or wraps round as
  an ordinary adder does.
- It reports an overflow flag, a zero flag and a negative flag with the sum. The sum is also on LED[15:0].
- CPU_RESETN resets everything to zero, which means unsigned and wrapping.
- Over the test shell (USB-UART, 115200 baud) I can set both numbers and the two settings, and read the sum and
  the flags. The design ID is "SADD".

Test hooks: top module `v2_a_sat_add_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
