# Stereo audio path with metering

I want the digital heart of an audio path, built for the Nexys A7-100T and meant to carry over to a board with an
audio codec later. Stereo audio comes in from a codec on I2S, is processed, and goes back out to the codec on I2S.
The codec generates the bit clock and the word-select clock, so the design only follows them; the design does
generate the codec's master clock.

- **Wiring (Pmod JA):** pin 1 `JA1` word select in (low = left), pin 2 `JA2` bit clock in, pin 3 `JA3` serial data
  in, pin 4 `JA4` serial data out, pin 7 `JA7` master clock out. The master clock is the board clock divided by 8, a
  square wave. (A real build would make 12.288 MHz with a clock generator; this task only needs the divided clock.)
- **Format:** standard (Philips) I2S, 24-bit samples, signed, 32 bit clocks per channel slot, bit clock 64 times the
  word rate, as in the receiver and transmitter blocks of the same family. The bit clock may stop between bursts.
- **Processing, per channel:** a gain and a mute. The gain is a 16-bit unsigned number in which 0x1000 means 1.0.
  Gain changes and mute are smoothed so there are no clicks: the gain actually applied moves toward its target by a
  fixed small amount each sample (the parameter `RAMP_STEP`, 16 by default) and stops exactly on it. Muting is a
  slide to zero, un-muting a slide back. A result that does not fit in 24 bits is limited to the nearest value that
  does.
- **Delay:** the frame that arrives in one frame period leaves, processed, in the next one. Before the first frame
  has gone through, the output is silence.
- **Metering, per channel, on the processed signal (after gain and mute):**
  - a peak meter with hold and decay: it jumps up at once to a louder sample, holds for a hold time that I can set
    (in samples, one setting for both channels), and then falls away;
  - an RMS meter over blocks of 2 to the power `RMS_LOG2` samples (8 by default), published when the block is done;
  - a clip counter, which counts samples at either end of the 24-bit range and stops at its largest value.
- **Registers (over the test shell, USB-UART, 115200 baud):** the gain of each channel, the two mute bits, the hold
  time, the two peaks, the two RMS readings, the two clip counts, a control register that clears the peaks and clip
  counts channel by channel, a count of frames received, a count of RMS blocks completed, and the gain currently
  applied on each channel.
- LED[7:0] shows the top 8 bits of the left peak and LED[15:8] the right peak.
- CPU_RESETN resets everything to its starting value (gains 1.0, mute off, meters zero, hold time 32).
- Take the board clock to be 8 to 100 times faster than the bit clock. Setting up the codec over I2C, and the codec
  board itself, are outside this task.
- The design ID is "APTH".

Test hooks: top module `v2_o_audio_path_top`, which has the parameters `RMS_LOG2` and `RAMP_STEP` besides the test
shell's `CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP`; its ports are named as in the board's master XDC.
