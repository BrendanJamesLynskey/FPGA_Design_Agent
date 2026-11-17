# RMS level meter

I want an RMS level meter for an audio path, on the Nexys A7-100T. Audio arrives as 24-bit signed samples; the meter
tells me the effective (root mean square) size of the signal over a block of recent samples, which is how loud it
sounds, as opposed to how big its single biggest spike was.

- The block is a fixed number of samples, a power of two: 2 to the power `RMS_LOG2`, with `RMS_LOG2` = 8 by default
  (256 samples, about 5 ms at 48 kHz). Blocks follow each other with no gap and no overlap.
- When a block is complete, the meter publishes one reading for it, as a 24-bit whole number, and keeps showing that
  reading until the next block completes. A count says how many blocks have been completed.
- The reading must be exact for the full range of the samples, up to a block that is all at the most negative value.
- I give it samples one by one; a write to the sample register is one sample period. Another register tells me how far
  through the current block it is.
- A control register lets me abandon the block in progress and start a fresh one, without touching the last reading.
- LED[15:0] mirrors the upper 16 bits of the reading.
- CPU_RESETN resets everything (reading and counts zero).
- All of it can be reached through the test shell on the USB-UART (115200 baud), whose design ID for this task is "RMSM".

Test hooks: top module `v2_o_rms_meter_top` with the parameter `RMS_LOG2`, ports named as in the board's master XDC,
and the test shell's `CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
