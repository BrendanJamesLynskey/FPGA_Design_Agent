# Addressable LED strip driver

I want to drive a strip of WS2812-style LEDs from the PC. They take one long serial stream on a single wire, with the
bits told apart by pulse width.

- I set a colour as 24 bits (red, green, blue, 8 bits each, 0xRRGGBB), a number of pixels (1 to 16) and a dimmer
  level, then say go. Every pixel on the strip gets the colour, scaled by the dimmer.
- The strip wants each pixel's colour sent green first, then red, then blue, most significant bit first. A 1 bit is
  a long high then a short low, a 0 bit is a short high then a long low. After the last pixel the line stays low
  for a while, which latches the colours.
- A go while a frame is still going out is ignored and counted.
- LED[0] follows the data line and LED[1] is lit while a frame (including the latch gap) is going out.
- Over the test shell (USB-UART, 115200 baud) I can set the colour, pixel count and dimmer, start a frame and read
  the status and the count of ignored goes. The design ID is "WS28".

Test hooks: top module `p_ws2812_gen_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `T0H`, `T0L`, `T1H`, `T1L` (high and low times of a
0 bit and a 1 bit, in clocks) and `RESET_CYCLES` (the low latch gap, in clocks) as top-level parameters.
