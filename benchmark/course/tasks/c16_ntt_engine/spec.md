# NTT engine behind the test shell

I want a block for the Nexys A7-100T's FPGA that computes the "number-theoretic transform" used in the post-quantum key-exchange standard FIPS 203 (ML-KEM), forwards and backwards, on a polynomial of 256 coefficients, and I want to exercise it entirely from the test shell.

- Every coefficient is a whole number from 0 to 3328 (arithmetic is modulo q = 3329). The transform is exactly the one in FIPS 203: "NTT" is algorithm 9 and "NTT inverse" is algorithm 10, including the final multiplication by 3303 at the end of the inverse.
- The block holds the 256 coefficients itself. I load them over the shell while the block is idle, two coefficients to a shell write, ask for a forward or an inverse transform with a start command, and read the 256 results back
  over the shell, two to a read, once the block says it is done. The transform replaces the coefficients (in place).
- The block must raise a "busy" signal while it works and a "done" flag at the end. A new request will not come while it is busy.
- Time limit: from the clock that takes the start request to the clock before the "done" pulse it must take no more than 1,200 clocks for either direction, and I can read back how many clocks the last transform took.
  Use no divide operators and no remainder operators (they do not belong in a design for this part), and no floating-point blocks.
- CPU_RESETN clears busy and done. I will check several transforms exactly: forward ones (a single one, all coefficients 3328, a random one) and an inverse (on a random polynomial).
  LED0 shows done and LED1 shows busy. The shell runs at 115200 baud on the USB-UART. The design ID is "NTTE".

Test hooks: top module `c16_ntt_engine_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters as top-level parameters. There are no other time
constants.
