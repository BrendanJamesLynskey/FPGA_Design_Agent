# Sound-level meter from the PDM microphone

I'd like a simple sound-level meter on the Nexys A7-100T using its PDM microphone, shown as a bar graph on the 16
LEDs, with the numbers readable over the test shell.

- Clock the microphone from the 100 MHz board clock divided down (a parameter sets the half period of M_CLK in
  clocks; about 2.5 MHz on the board). Use the microphone channel that has M_LRSEL driven high, and take the data
  on the correct clock edge for that channel.
- Count the ones in each block of a fixed number of bits (a parameter). Silence gives about half ones, so the level
  of a block is how far the count is from half the block size.
- Keep a peak value that holds for a while after a loud block and then falls back slowly; how long it holds and how
  fast it falls should be settable.
- LEDs: a bar graph of the level, all 16 lit at full scale.
- Registers for the level, the peak (which I can reset), the settings, and how many blocks have gone by.
- Design ID "PDMV".

Test hooks: top module `t2_pdm_vu_top`, ports named as in the board's master XDC (`M_CLK`, `M_DATA`, `M_LRSEL`,
`LED`, the USB-UART pins, `CLK100MHZ`, `CPU_RESETN`), the test shell's `CLKS_PER_BIT`, `TIMEOUT_CYCLES` and
`BUILD_STAMP` parameters, plus `CLK_HALF` (M_CLK half period in clocks) and `WINDOW` (bits per block, a multiple
of 32) as top-level parameters.
