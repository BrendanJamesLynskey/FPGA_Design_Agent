# Droop-compensating FIR for an audio decimator

Next in a PDM microphone chain after the CIC filter comes a small FIR filter that lifts the high end of the audio
band back up, because the CIC rolls it off. I want that one filter on the Nexys A7-100T as a block I can test on
its own.

- Samples are 16-bit signed numbers. I write one sample at a time through the test shell, and the filter gives one
  result for each sample written.
- It is a short symmetric filter, nine taps, with whole-number coefficients that add up to a power of two so that
  steady signals pass at the same level. The history starts at zero.
- The results are 16-bit signed numbers. Round to the nearest, and a result that does not fit must stop at the
  largest or smallest value instead of wrapping; I want to be told that this happened.
- Results wait in a short queue that I read from the shell. If I do not read them fast enough, keep the newest and
  tell me.
- A clear command puts everything back to the starting state. CPU_RESETN resets everything.
- The design ID is "CFIR". Ask me for the coefficients, the sizes and any other detail you need.

Test hooks: top module `v2_b_comp_fir_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
