# 4 x 4 row multiplier behind the test shell

I want a block for the Nexys A7-100T's FPGA that multiplies short rows of numbers by a fixed small table of numbers, as fast as one row per clock, and I want to exercise it entirely from the test shell.

- The table is 4 by 4 signed 8-bit numbers. I load it once with a "load" command: all 16 numbers are loaded over the shell and applied together, and later a new table can be loaded the same way (not
  while rows are being processed).
- A row is four signed 8-bit numbers presented together. Because the shell is slow, I can park up to 16 rows over the shell and then give a "burst" command with a row count; the block then presents those rows
  to the arithmetic on consecutive clocks, with no gaps, and keeps the results in order.
- For each row, the block gives four signed results (each is the sum of the four row numbers times the four numbers of one column of the table, so each needs more than 8 bits; keep each as a
  32-bit signed number). I read them back over the shell after the burst, and a flag tells me when all of them are in.
- The results for a row must be ready within 8 clocks of the row being presented; every row must give its answer, in order, with no row lost even when rows come on consecutive clocks. I can read
  back how many clocks the first row took.
- CPU_RESETN clears everything. Exact results only: I will compare every number with my own calculation. LED0 shows the done flag. The shell runs at 115200 baud on the USB-UART. The design ID is "MM4X".

Test hooks: top module `c14_systolic_matmul_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters as top-level parameters. There are no other time
constants.
