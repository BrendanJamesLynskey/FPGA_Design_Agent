# Half-band decimate-by-two stage

The second rate change in a microphone chain: a stage that halves the sample rate of a stream of 16-bit audio
samples, using a short half-band low-pass filter so that what lies above the new Nyquist frequency does not fold
back into the band. I want that one stage on the Nexys A7-100T so I can check it by itself on the bench.

- Samples are 16-bit signed numbers. I write them one at a time through the test shell; every second sample written
  produces one result, so the result rate is half the input rate.
- The filter is seven taps long with whole-number coefficients, symmetric, with every second coefficient zero except
  the centre one, and the coefficients sum to a power of two so that steady signals keep their level. The history
  starts at zero.
- The result is a 16-bit signed number. Round it with the convergent rule that avoids a bias, and stop at the
  largest or smallest value instead of wrapping; I want to know if that happened.
- Results go into a small queue that I read from the shell. If a result arrives when the queue is full, tell me
  what happened.
- A clear command returns everything to the starting state, including which of the two samples is next. CPU_RESETN
  resets everything.
- The design ID is "HBDC". Ask me for the coefficients, which of the two samples produces the result, the sizes,
  and anything else you need.

Test hooks: top module `v2_b_halfband_dec_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
