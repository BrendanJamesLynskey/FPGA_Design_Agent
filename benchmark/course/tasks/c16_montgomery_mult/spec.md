# Montgomery multiplier behind the test shell

I want a block for the Nexys A7-100T's FPGA that multiplies two 64-bit numbers modulo a third, in the "Montgomery" way public-key cryptography uses, and I want to exercise it entirely from the test shell.

- Inputs: a, b and n, each 64 bits, with n odd and a and b smaller than n, loaded over the shell, and a "start" command that requests the product for one clock.
- Output: r = a x b x 2^-64 mod n, that is, the number r smaller than n for which r x 2^64 leaves the same remainder as a x b when divided by n. A "done" flag says r is ready; "busy" is high between the start and the done.
  r keeps its value until the next start. A new start will not come while it is busy.
- **The number of clocks from start to done must be exactly the same for every input** (zero operands, operands equal to n minus one, and everything in between), and no more than 100. This is a security requirement: the time must
  not tell an observer anything about the numbers. The block measures this and I can read the number of clocks of the last product.
- No divide operators and no remainder operators, and no floating-point blocks. CPU_RESETN clears the loaded numbers, busy and done.
- I will check a few dozen products exactly, with moduli of 64 and of 40 bits, and I will compare the number of clocks of all of them. LED0 shows done and LED1 shows busy.
  The shell runs at 115200 baud on the USB-UART. The design ID is "MONT".

Test hooks: top module `c16_montgomery_mult_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters as top-level parameters. There are no other time
constants.
