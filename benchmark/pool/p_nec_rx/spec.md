# Infrared remote receiver

I want to read a TV-remote-style signal with an IR receiver module wired to Pmod JC pin 2.

- The receiver module has already removed the carrier. Its output is high when nothing is being sent and goes low for
  the "marks" of the code. So the code is seen as low pulses (marks) and high gaps (spaces).
- The code is the NEC style: a long leader mark and space, then 32 bits, then a final mark. Each bit is a short mark
  and then a short space for a 0 or a longer space for a 1. The bits are the address, its complement, the command and its
  complement, each byte least significant bit first. A leader followed by a shorter space and one mark is a repeat code.
- Timing in real remotes drifts, so the design must accept lengths that are only roughly right, within sensible
  windows, and must reject frames that are clearly broken: a wrong complement byte or a pulse of a wrong length is an
  error, counted under its own heading.
- LED[7:0] show the last good command and LED[15:8] the address.
- Over the test shell (USB-UART, 115200 baud) I can read the address and command of the last good frame and the counts of
  good frames, repeat codes and the two kinds of error, and clear the counts. The design ID is "NECR".

Test hooks: top module `p_nec_rx_top`, ports named as in the board's master XDC, the test shell's `CLKS_PER_BIT`,
`TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `UNIT_CYCLES` (the basic time unit, 562.5 microseconds, in clocks) as a
top-level parameter.
