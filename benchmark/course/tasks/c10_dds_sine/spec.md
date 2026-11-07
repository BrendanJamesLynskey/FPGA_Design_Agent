# Sine-wave generator behind the test shell

I want a numerically controlled sine oscillator for the Nexys A7-100T's FPGA, to drive a DAC test: a frequency word in, a sampled sine wave out, one sample per clock. I want to exercise it entirely from the test shell.

- The frequency word `fw` is 24 bits: the output frequency is `fw / 2^24` times the clock rate; it can change at any clock. The output is a signed 12-bit sample with a valid flag.
- The phase is a 24-bit counter that advances by `fw` every clock and wraps. The sine comes from a table of 256 entries covering one full cycle: entry `i` is `floor(2047 * sin(2 * pi * i / 256) + 0.5)`. The table is addressed by the top 8 bits of the phase (the lower bits are simply dropped, no interpolation or dithering).
- The first output after the oscillator is reset is table entry 0 (phase 0); at each following clock the phase has advanced by the `fw` of the previous clock. The valid flag is low during reset and high from the first clock after it.
- CPU_RESETN clears the oscillator and the loaded values.
- The block must close timing at 100 MHz.
- Over the shell I load `fw` and give a "go". A "go" resets the oscillator and records the next 1,200 valid samples, the first being the first output after that reset. Afterwards I read the 1,200 samples back, two per register read (an auto-incrementing read port), and a flag that says the recording is finished. I will run it with several frequency words and compare every sample.
- The shell runs at 115200 baud on the USB-UART. The design ID is "DDSN".

Test hooks: top module `c10_dds_sine_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters as top-level parameters. There are no other time
constants.
