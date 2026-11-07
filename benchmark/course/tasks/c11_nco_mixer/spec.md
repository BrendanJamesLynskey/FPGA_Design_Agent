# NCO and mixer for a radio front end, behind the test shell

I am building the first stage of a digital down-converter for the Nexys A7-100T's FPGA: take a stream of signed 12-bit real samples `x`, multiply them by a complex tone `exp(-j * phase)` that I can set the frequency of, and give the two products out as `i_out` and `q_out`, so a signal at the oscillator's frequency lands at zero hertz. I want to exercise it entirely from the test shell.

- A sample `x` (signed 12 bits) is presented on any clock (an "enabled" clock); when no sample is presented everything holds, including the phase. The frequency word `fw` is 16 bits: the tone frequency is `fw / 2^16` times the rate of enabled samples. A result is the pair `i_out`, `q_out` (signed 12 bits each) and appears exactly one clock after each enabled clock, and on no other clock.
- The phase is a 16-bit accumulator, 0 after reset, advancing by `fw` on each enabled clock, wrapping. The sine and cosine come from one table of 256 entries covering a full cycle: `S[k] = floor(16383 * sin(2 * pi * k / 256) + 0.5)` (signed, 16 bits); the cosine of an index `k` is `S[(k + 64) mod 256]`. The index is the top 8 bits of the phase **before** that clock's advance (lower bits dropped).
- For each enabled sample with sine `s` and cosine `c`: `i_out = floor(x * c / 2^14)` and `q_out = floor(-x * s / 2^14)` (floor = arithmetic shift right, rounding towards minus infinity), as 12-bit signed values.
- CPU_RESETN clears the oscillator phase and the loaded values.
- The block must close timing at 100 MHz.
- Over the shell I set `fw`, load up to 16 samples, give a 32-bit pattern that says on which of the next 32 clocks a sample is presented (a 1 bit presents the next sample, in order), and a "go". The phase keeps running from one such burst to the next. Afterwards I read the result pairs in order, how many came out, and a 32-bit record of the clocks on which a result appeared. I will send 1,500 samples (random values, a tone, full-scale values) with gaps where no sample is presented and with a couple of frequency words, and compare every output pair.
- The shell runs at 115200 baud on the USB-UART. The design ID is "NCOM".

Test hooks: top module `c11_nco_mixer_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters as top-level parameters. There are no other time
constants.
