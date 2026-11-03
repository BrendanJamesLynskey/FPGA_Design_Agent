# Manchester receiver

I want to receive bytes that another board sends on Pmod JB pin 1 in a Manchester-coded frame.

- A frame is a lead-in of four 1 bits then a 0 bit, then eight data bits least significant bit first, then a parity bit
  that makes the nine bits even. A 1 bit is low then high, a 0 bit is high then low, and the line is low when idle.
- Every bit must have its mid-bit transition. A frame in which one bit has none, or in which the lead-in is wrong, is
  rejected and counted under its own heading; a frame with a good lead-in and a good transitions but a wrong parity bit
  is counted as a parity error. A good frame updates the received byte and is counted.
- When a frame is over, good or bad, the receiver wants to see the line quiet and low for a couple of bit times
  before it looks for the next one.
- LED[7:0] show the last good byte, LED[15:8] the number of good frames (low eight bits).
- Over the test shell (USB-UART, 115200 baud) I can read the last byte and the four counts. The design ID is "MCRX".

Test hooks: top module `p_manchester_rx_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `BIT_CYCLES` (clocks in one bit, a multiple of 4)
as a top-level parameter.
