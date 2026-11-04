# Manchester transmitter

I want to send bytes from the PC out on Pmod JB pin 1 as a Manchester-coded frame, for a small wired link.

- A frame is a lead-in, the byte and a check bit. The lead-in is four 1 bits and then a 0 bit, so a receiver
  can find the start of the frame. The byte goes next, least significant bit first, and then one parity bit that makes
  the number of 1s among the eight data bits and the parity bit even.
- Manchester coding: every bit has a transition in the middle. A 1 is low in the first half of the bit and high in the
  second half; a 0 is high first and low second. The line sits low when idle and goes back to low when the frame
  ends.
- A byte written while a frame is still going out is not queued: it is dropped and counted.
- LED[0] follows the line, LED[1] is lit while a frame is going out.
- Over the test shell (USB-UART, 115200 baud) I write the byte to send and read the count of frames sent, the count
  of drops and whether it is busy. The design ID is "MCTX".

Test hooks: top module `p_manchester_tx_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `BIT_CYCLES` (clocks in one bit, an even number)
as a top-level parameter.
