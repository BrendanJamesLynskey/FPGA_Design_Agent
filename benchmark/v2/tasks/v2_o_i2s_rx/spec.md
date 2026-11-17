# I2S audio receiver

I want the input side of a digital audio link, on the Nexys A7-100T. A codec chip sends me stereo audio on three wires,
the standard I2S way, and I want to get the samples out of it. The codec generates the clocks; I only listen.

- Pmod JA pin 1 is the word-select line `JA1` (low while the left channel is sent, high for the right), pin 2 is the
  bit clock `JA2`, and pin 3 is the serial data `JA3`. All three are inputs.
- The format is the standard (Philips) I2S one: each channel's slot is 32 bit clocks long, the sample is 24 bits sent
  most significant bit first, signed, and the rest of the slot is padding. The bit clock runs at 64 times the word
  rate, and it may be stopped for a while between bursts of audio.
- A sample counts as received when its last bit has been captured. I want the latest left sample and the latest right
  sample in registers, as signed numbers, and a count of the stereo frames received.
- A control register lets me clear the frame count.
- LED[15:0] shows the top 16 bits of the left sample.
- CPU_RESETN resets everything to zero.
- Assume the board clock runs between 8 and 100 times faster than the codec's bit clock.
- I reach it all through the test shell (USB-UART, 115200 baud); the design ID is "I2SR".

Test hooks: the test shell's `CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters; ports named as in the
board's master XDC; top module `v2_o_i2s_rx_top`.
