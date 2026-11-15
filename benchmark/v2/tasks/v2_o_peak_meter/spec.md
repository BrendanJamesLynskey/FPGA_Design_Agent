# Peak meter with hold and a clip counter

I want the level meter of an audio path on the Nexys A7-100T. Audio arrives as 24-bit signed samples, and I want to
see how loud the loudest recent sample was, the way a recording desk does: the reading jumps up at once to a new loud
sample, stays put for a short while, and then falls away smoothly, so I can read it by eye. Separately I want a count
of how many samples ran into the end of the range, so that I know whether the signal clipped.

- The meter reading is the size (magnitude) of the loudest sample, as a 24-bit number. A louder sample raises the
  reading to its size immediately. The reading then stays there for a hold time that I can set (counted in samples),
  after which it falls by a fraction of itself on every sample.
- A clip is a sample sitting at either end of the 24-bit range. The clip counter counts them, 16 bits wide, and it
  stops at its largest value instead of wrapping round.
- Samples go in one at a time, and every write to the sample register stands for one sample period.
- One control register clears the reading and clears the clip counter, each on its own.
- LED[15:0] shows the top 16 bits of the reading.
- CPU_RESETN resets everything to its starting value (reading and count zero).
- Everything is reachable over the test shell (USB-UART at 115200 baud); the design ID is "PEAK".

Test hooks: top module `v2_o_peak_meter_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
