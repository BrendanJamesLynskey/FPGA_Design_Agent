# One-bit DAC

I want to turn an 8-bit number from the PC into a voltage, using the audio output as a one-bit DAC. The audio output
filter will average the pulses.

- The number is VALUE, 0 to 255. AUD_PWM is a stream of ones and zeros, one per clock, whose density is VALUE/256: out of
  every 256 clocks exactly VALUE are ones, spread as evenly as possible by the usual accumulator trick (first-order
  sigma-delta), not as one fat pulse.
- SW[15] up enables the output and the audio amplifier through AUD_SD. With it down the output is held low and the
  amplifier is off.
- SW[0] up inverts the stream (density 1 - VALUE/256).
- LED[7:0] show VALUE; LED[15] shows the enable.
- Over the test shell (USB-UART, 115200 baud) I can set and read VALUE. The design ID is "SDDA".

Test hooks: top module `p_sigma_delta_dac_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
