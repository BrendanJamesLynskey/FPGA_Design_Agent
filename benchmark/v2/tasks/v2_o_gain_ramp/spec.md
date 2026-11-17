# Click-free gain control

I want the volume control of an audio path, built for the Nexys A7-100T. Audio arrives as 24-bit signed samples and
the control scales each one by a gain. The gain must never jump: when I change it, or press mute, the volume has to
slide to the new setting over many samples, because a sudden step in gain is heard as a click.

- The gain is a 16-bit unsigned number in which 0x1000 means exactly 1.0 (no change). The setting I write is the
  target; the gain actually applied moves toward it by the same fixed amount on every sample, and stops exactly on
  it. The amount is the parameter `RAMP_STEP`, 16 by default.
- A mute control makes the target zero without forgetting the setting; releasing it brings the gain back to the
  setting by the same slide.
- If the scaled sample does not fit in 24 bits, it is limited to the nearest value that does.
- I feed it one sample at a time: each write of a sample to the sample register is one sample period. The scaled
  sample can then be read back, along with the gain that was applied and a status register that says whether the
  gain is still moving and whether the last sample had to be limited.
- LED[15:0] shows the top 16 bits of the scaled sample.
- CPU_RESETN resets everything: gain and setting back to 1.0, mute off, outputs zero.
- Over the test shell (USB-UART, 115200 baud) I can reach all of this. The design ID is "GRMP".

Test hooks: top module `v2_o_gain_ramp_top` with the parameter `RAMP_STEP`, ports named as in the board's master
XDC, and the test shell's `CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
