# Softmax unit behind the test shell

I want a block for the Nexys A7-100T's FPGA that turns eight scores into eight probabilities the way a neural network does ("softmax"): each probability is e raised to the power of its score, divided by the sum of those
numbers over all eight, so the eight probabilities add up to one and a bigger score gets a bigger probability. I want to exercise it entirely from the test shell.

- The input is eight scores loaded over the shell, each a signed 16-bit number that is the real score times 256 (so 256 means a score of 1.0, -128 means -0.5), followed by a "go" command.
- The output is the eight probabilities that I read back over the shell, each an unsigned 16-bit number that is the probability times 32768 (so 32768 means 1.0), with a flag that says they are ready.
- The scores can be anywhere in the 16-bit range, including all eight equal, one score far above the rest, and large values that would overflow a naive calculation (adding the same amount to every score must not change
  the answer). Use no floating-point blocks and no division blocks; a few small tables and multipliers are fine.
- Accuracy I need: every probability within 1/128 of the true value, and the eight probabilities adding up to 1 within 1/128. Anything inside that is acceptable; I do not need a particular design.
- I will check the outputs for a few dozen score sets against my own calculation with real numbers. CPU_RESETN clears the loaded scores and the ready flag. LED0 shows the ready flag.
  The shell runs at 115200 baud on the USB-UART. The design ID is "SMAX".

Test hooks: top module `c15_softmax_unit_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters as top-level parameters. There are no other time
constants.
