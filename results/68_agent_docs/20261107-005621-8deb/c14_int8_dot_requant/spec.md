# Quantised-layer arithmetic unit behind the test shell

I want a block that does the arithmetic of one output of a quantised neural-network layer, for the Nexys A7-100T's FPGA, and I want to exercise it entirely from the test shell.

- It takes eight activation numbers and eight weight numbers, all signed 8-bit (activations -128 to 127, weights -127 to 127), plus a signed 32-bit bias, a 16-bit unsigned multiplier "mult",
  a shift "shift" (1 to 31) and a one-bit "relu" switch. I load these over the shell and then give a "go" command that presents them to the block for one clock.
- It multiplies the eight pairs, adds the eight products and the bias, and calls the total "acc".
- It then scales acc by the fraction mult / 2^shift, rounding to the nearest whole number with exact halves going up (towards plus infinity; for example 2.5 gives 3 and -2.5 gives -2),
  and limits the answer to the range -128 to 127 (to 0 to 127 when relu is 1).
- When the work is done I can read the limited answer y (signed 8-bit) and, as a second output, acc (signed 32-bit), and a flag that says the result is ready.
- It must be exact: I will compare every output with my own calculation, including extreme inputs, results that need limiting at both ends and exact halves. CPU_RESETN clears the loaded numbers and the ready flag.
- LED0 shows the ready flag. The shell runs at 115200 baud on the USB-UART. The design ID is "DOTQ".

Test hooks: top module `c14_int8_dot_requant_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters as top-level parameters. There are no other time
constants.
