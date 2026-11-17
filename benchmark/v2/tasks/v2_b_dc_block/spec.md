# DC blocker for a microphone signal

A PDM microphone has a small constant offset, and after the filters it shows up as a DC level in the audio. I want a
DC blocker at the end of the chain on the Nexys A7-100T, as a block I can test on its own.

- Samples are 16-bit signed numbers, written one at a time through the test shell; every sample written gives one
  result.
- It is a first-order high-pass filter: the result follows the change in the input, and a steady input level fades
  away. Use a pole very close to one, set by a power of two so it needs no multiplier.
- The result is a 16-bit signed number. If the calculation does not fit, stop at the largest or smallest value
  instead of wrapping, and tell me it happened.
- Results wait in a short queue that I read from the shell. If I am too slow, keep the newest ones and tell me.
- A clear command returns everything to the starting state. CPU_RESETN resets everything.
- The design ID is "DCBK". Ask me for the exact equation, how the arithmetic is rounded, the pole and the sizes.

Test hooks: top module `v2_b_dc_block_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
