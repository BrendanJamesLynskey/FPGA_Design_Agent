# Safe PWM audio output stage for the Nexys A7 speaker jack

The Nexys A7-100T has a mono audio output driven by a single pin (`AUD_PWM`) that feeds a low-pass filter and an amplifier (enabled by the pin `AUD_SD`). I want an output stage that takes signed 16-bit audio samples and turns them into a pulse-width-modulated waveform on that pin, with a volume control that cannot hurt anybody's ears.

- The audio sample is a signed 16-bit number that may be changed at any time and is held between samples. There is a gain register and a way to write it. The sample after the volume, `sample_out` (signed 16 bits), is available combinationally from the sample and the gain register.
- `AUD_PWM` is open-drain style: the design pulls the pin low or lets it go (high impedance), and the board's pull-up floats it high; the pin is never driven high. `AUD_SD`, the amplifier enable, is always high.
- Volume: the gain register is unsigned Q15 (32768 = unity), `sample_out = floor(sample * gain / 2^15)`. It resets to **2068** (about -24 dBFS). Writing a value sets it, but any value above **8192** (about -12 dBFS) is replaced by 8192, so the output can never be louder than -12 dBFS whatever is written.
- PWM: a free-running 10-bit counter divides the clock by 1024 (97.7 kHz carrier). The pin is pulled low on the clocks where the counter is at or above the duty value, and released below it, so in each period the pin is pulled low for 1024 minus the duty clocks. The duty value is `512 + floor(sample_out / 128)` (mid-scale 512 for silence), updated once per period.
- CPU_RESETN resets the gain to its default and clears the sample.
- The block must close timing at 100 MHz.
- Over the shell I write the sample, write the gain, and read `sample_out` back. I will exercise it in simulation (reset, default gain, writes of 65535, 4000, 8192, 8193, a reset after a write; sample values of 0, +32767, -32768 and others; each held for several periods) and compare `sample_out`, the number of clocks the pin is pulled low per period (measured on the `AUD_PWM` pin), and `AUD_SD`.
- The shell runs at 115200 baud on the USB-UART. The design ID is "PWMA".

Test hooks: top module `c12_nexys_pwm_audio_top`, ports named as in the board's master XDC (`AUD_PWM`, `AUD_SD`, the USB-UART pins, `CLK100MHZ`, `CPU_RESETN`, and the 16-bit `LED` output, which the block leaves off), and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters as top-level parameters. There are no other time constants.
