# RMS norm unit behind the test shell

I want a block for the Nexys A7-100T's FPGA that rescales a vector of 16 numbers so that its root-mean-square value becomes 1 (the "RMS norm" a neural network applies before each layer), and I want to exercise it entirely from the test shell.

- The input is 16 numbers loaded over the shell, each a signed 16-bit number that is the real value times 256 (so 256 means 1.0), followed by a "go" command. The output is 16 numbers in the same format (real value times 256) that I read back
  over the shell, with a flag that says they are ready.
- Each output is the input divided by the square root of (the mean of the squares of the 16 inputs, plus a tiny constant 1/65536, in real units). The tiny constant makes an all-zero input give an all-zero output.
- Inputs range from a few units in the last place up to full scale, and the 16 numbers can have very different sizes (one big, fifteen zero). No floating-point blocks and no divider blocks; tables and multipliers
  are fine.
- Accuracy I need: every output within 1 unit of the last place (1/256) of the true value (rounded as you like).
- I will check the outputs for a few dozen input vectors against my own calculation with real numbers. CPU_RESETN clears the loaded inputs and the ready flag. LED0 shows the ready flag.
  The shell runs at 115200 baud on the USB-UART. The design ID is "RMSN".

Test hooks: top module `c15_rmsnorm_unit_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters as top-level parameters. There are no other time
constants.
