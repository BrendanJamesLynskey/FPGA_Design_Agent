# I2S audio transmitter

I want the output side of a digital audio link, on the Nexys A7-100T. I have a stereo sample pair that I want to send
to a codec chip on three wires, the standard I2S way. The codec generates the clocks, so the design is a listener on
two of the wires and a talker on the third.

- On Pmod JA, `JA1` (pin 1) and `JA2` (pin 2) come from the codec: word select, low for the left channel and high for
  the right, and the bit clock. `JA4` (pin 4) is the serial data I send, an output.
- The format is Philips I2S: a channel slot lasts 32 bit clocks and carries one signed 24-bit sample, most significant
  bit first, padded to fill the slot. The bit clock is 64 times the word rate and may stop between bursts of audio.
- I set the left and right samples in two registers. Nothing changes on the wire until I say so with a commit
  command in a control register; the pair is then sent, left and right together, starting with the next frame, and
  the same pair is sent again in every following frame until I commit a new one. A pair I am still writing must never
  be half-sent.
- A count says how many frames have been started, and the control register can clear it.
- Until the first commit, and after a reset, the data line sends silence (zeros).
- LED[15:0] shows the top 16 bits of the left sample being sent.
- CPU_RESETN resets everything to zero.
- Assume the board clock is 8 to 100 times faster than the codec's bit clock, no more.
- All of this is reached over the test shell, on the USB-UART at 115200 baud, and the design ID is "I2ST".

Test hooks: top module `v2_o_i2s_tx_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
