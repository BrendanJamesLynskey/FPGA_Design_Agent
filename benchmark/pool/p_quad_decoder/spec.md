# Quadrature decoder

I am testing an encoder reader, and for now the encoder is me flipping switches.

- SW[1] is channel A and SW[0] is channel B of a quadrature encoder. Walking the pair through 00, 01, 11, 10 and
  round again is forward; walking it the other way is backward. Every single change of the pair is one count.
- A change where both channels flip at the same moment cannot be told apart from forward or backward, so it must not move
  the position; it just gets counted as an error.
- SW[2] is the index: each time it goes from down to up the position is set back to zero.
- LED[15:0] show the position as a 16-bit two's-complement number.
- Over the test shell (USB-UART, 115200 baud) I can read and set the position, read how many forward counts, backward
  counts and errors there have been, and read which way the last count went. The design ID is "QDEC".

Test hooks: top module `p_quad_decoder_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
