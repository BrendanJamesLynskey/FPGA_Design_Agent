# Oracle ambiguity list for v2_o_i2s_rx (what spec.md leaves out on purpose)

1. Which of the several I2S-like formats: Philips I2S, MSB one bit clock after the word-select edge (spec.md says "the
   standard I2S way" and "the standard (Philips) I2S one").
2. Which edge samples SDI (rising), and which edge the codec changes LRCK and SDI on (falling).
3. When a frame is complete (when the right sample has been captured) and what FRAMES counts.
4. Register offsets, widths, sign extension on read, reset values, what the control does.
5. Whether the padding bits are checked (they are not).
6. The bit-clock ratio the bench uses (the board clock is 12 times faster than the bit clock); spec.md gives the allowed range 8 to 100.
