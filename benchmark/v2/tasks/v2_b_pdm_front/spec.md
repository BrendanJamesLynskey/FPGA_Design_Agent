# PDM microphone front end

The first block of a microphone chain on the Nexys A7-100T: it clocks the on-board PDM microphone, takes in its
one-bit stream and hands the bits to the rest of the design packed into words. I want to check it on the bench by
playing a known bit pattern into the microphone pin and reading the words back.

- Make the microphone clock from the 100 MHz board clock; a parameter sets its half period in board clocks (about
  3 MHz on the board). Use the microphone channel that has M_LRSEL driven low, and take each data bit at the right
  moment for that channel.
- The clock only runs while I have the run setting on. Switching it off stops the clock low and abandons any
  word that is half built.
- Pack 32 bits into each word, the first bit taken going into the lowest bit. Finished words go into a short queue
  that I read from the shell.
- A microphone that is unplugged or dead sends a constant level. Tell me if the stream has been stuck at one
  level for a stretch, and which level; the flag should stay on until I clear it.
- If the queue is full when a word is finished, tell me that something was lost.
- Show whether the clock is running and whether the stream is stuck on the LEDs.
- CPU_RESETN resets everything. The design ID is "PDMF". Ask me about anything else you need (the register layout,
  the queue depth, how long a stretch is).

Test hooks: top module `v2_b_pdm_front_top`, ports named as in the board's master XDC (`M_CLK`, `M_DATA`,
`M_LRSEL`, `LED`, the USB-UART pins, `CLK100MHZ`, `CPU_RESETN`), the test shell's `CLKS_PER_BIT`, `TIMEOUT_CYCLES`
and `BUILD_STAMP` parameters, and one more top-level parameter, `CLK_HALF`, which is the half period of M_CLK counted in board clocks.
