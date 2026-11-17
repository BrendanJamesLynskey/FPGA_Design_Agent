# CIC decimator for a one-bit audio stream

I need the first filter stage of a PDM microphone chain on the Nexys A7-100T: a CIC decimator that turns a stream of
one-bit samples into a slower stream of multi-bit numbers. I want to feed it a block of bits at a time and read the
results back, so I can check it against a model on the bench.

- Three integrator stages, a decimation by 16, then three comb stages. Treat a 1 as +1 and a 0 as -1. No scaling:
  I want the exact number the filter produces.
- Bits go in 32 at a time through a register, and the filter takes them one per clock. Results go into a small
  queue that I read from the shell, one at a time.
- I only want results that are made entirely from real input bits. The filter starts empty after a reset or a
  clear, and what it produces while it is still filling is not a result.
- If the queue is full when a result arrives, tell me that something was lost.
- A clear command puts the filter, the queue and the lost-result flag back to the starting state.
- CPU_RESETN resets everything.
- The design ID is "CICD". Ask me about anything else you need (the exact register layout, the queue depth, what
  happens at the edges).

Test hooks: top module `v2_b_cic_decim_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
