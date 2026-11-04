# Error-correcting code codec

I want a codec I can poke from the PC to experiment with error correction. It encodes four data bits into an eight-bit
word that survives one flipped bit, and tells me when two bits were flipped.

- The code is the usual Hamming code on seven positions numbered 1 to 7, with the check bits at positions 1, 2 and 4
  and the four data bits in the rest, plus an extra overall parity bit so that two errors can be detected.
- The encoder is a register: write four bits, read the codeword. The decoder is another: write a received word, read
  the data bits back corrected if possible, with the syndrome and whether it fixed one error or found two.
- With two errors the data is passed through as received, not guessed.
- I want counts of single and double errors seen. LED[7:0] show the last codeword the encoder made, LED[11:8] the
  last decoded data and LED[13:12] a result code: 0 clean, 1 one error fixed, 2 two errors.
- The design ID is "HAM8".

Test hooks: top module `p_hamming84_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
