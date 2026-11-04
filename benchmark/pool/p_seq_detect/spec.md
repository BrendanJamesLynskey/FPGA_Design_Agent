# Serial pattern detector

I want to feed a bit stream in by hand and have the board spot a pattern in it.

- SW[0] is the data line. At a steady sampling rate the design takes a bit from it, and looks for a pattern of up to
  eight bits in the most recent bits. Matches may overlap: in 1011011 the pattern 1011 is found twice.
- I can set the pattern and its length over the test shell (USB-UART, 115200 baud). The first bit sent is the oldest, so the
  pattern is written with its oldest bit as the most significant of its length. It starts as 1011.
- SW[1] up makes it look for the opposite of the pattern (every bit flipped) instead.
- SW[2] up holds the detector: no bits are taken in and nothing counts, so I can read things in peace.
- LED[0] shows whether the latest bit completed a match, and LED[1] flips at every sampling instant so I can see
  the rate. I can read the last eight bits, the number of matches and the number of bits taken in, and clear them.
- The design ID is "SQDT".

Test hooks: top module `p_seq_detect_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `SAMPLE_CYCLES` (clocks between samples) as a
top-level parameter.
