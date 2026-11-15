# PDM microphone to 48 kHz audio

I want the audio side of the Nexys A7-100T's PDM microphone: the one-bit stream from the microphone turned into
ordinary 16-bit audio samples at about 48 kHz, good enough to listen to. Everything is built in the FPGA from the
100 MHz board clock; I will read the samples back over the test shell.

- Clock the microphone from the board clock (a parameter sets the half period of its clock in board clocks; about
  3 MHz on the board) and use the channel that has M_LRSEL driven low.
- Turn the bit stream into audio with a low-pass decimation chain: a CIC filter first, then two half-band stages
  that each halve the rate, then a short FIR that lifts the top of the band back up, and a DC blocker at the end.
  The total rate reduction is 64. Keep the arithmetic exact and the numbers inside 16 bits, stopping at the limits
  instead of wrapping, and tell me if that ever happened.
- Audio quality: the level should be flat across the speech and music band, tones that would fold into that band
  from above must be strongly attenuated, and the noise must be low enough for a quiet room.
- A capture memory records the first stretch of audio after I ask for it, so I can read it back at my own pace.
  Show whether the chain is running, whether a capture is complete and whether anything hit a limit on the LEDs.
- The microphone clock only runs while the run setting is on; switching run on always starts the chain from empty.
- CPU_RESETN resets everything. The design ID is "PDMC". Ask me about anything else you need: the filter
  coefficients, the scaling, the capture and register details, and the exact quality numbers.

Test hooks: top module `v2_b_pdm_chain_top`, ports named as in the board's master XDC (`M_CLK`, `M_DATA`,
`M_LRSEL`, `LED`, the USB-UART pins, `CLK100MHZ`, `CPU_RESETN`), the test shell's `CLKS_PER_BIT`, `TIMEOUT_CYCLES`
and `BUILD_STAMP` parameters, plus the top-level parameter `CLK_HALF`: how many board clocks make half a period of the microphone clock.
