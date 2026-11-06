# Hough line accumulator behind the test shell

I want a block that is told where the edge points of a small picture are and then tells me which straight lines they form, and I want to exercise it entirely from the test shell.

- The picture is 32 by 32. I give the block the edge points one at a time over the shell: x and y (0 to 31) in one write, which presents the point to the block for one clock; the block takes a new point only when it is not busy,
  and it says so in a status register.
- The block looks for lines at 16 directions spaced evenly over 180 degrees (0, 11.25, 22.5 ... degrees, the angle of the line's normal) and records, for each direction, how many points would lie on
  each possible distance from the origin (whole numbers, from -48 to +47). I want to be able to read any of these counts back: I select a direction and a distance and then read the count.
- A "clear" command starts a new picture by zeroing all counts.
- I will test it with pictures of single straight lines at known angles, and with several lines at once. CPU_RESETN returns the block to idle. LED0 shows that the block is busy.
  The shell runs at 115200 baud on the USB-UART. The design ID is "HOUG".

Test hooks: top module `c13_hough_lines_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters as top-level parameters. There are no other time
constants.
