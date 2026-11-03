# HDLC-style frame transmitter

I want to send little frames from the PC out on Pmod JC pin 1 in the bit-oriented style of HDLC.

- I load up to eight payload bytes into a buffer over the test shell, then tell it to send. It sends a flag
  (01111110), the payload, a two-byte frame check and a closing flag.
- Every byte goes out least significant bit first. The frame check is the 16-bit CRC used by HDLC (CRC-16/X-25) over
  the payload, sent low byte first.
- So that a flag can never appear inside the frame, the sender inserts a 0 after any five 1s in a row in the payload
  and check bytes (not in the flags).
- The line sits high when idle. A byte offered to the buffer when it is full or while a frame is going out is dropped
  and counted.
- LED[0] follows the line and LED[1] is lit while a frame is going out.
- Over the test shell (USB-UART, 115200 baud) I can load and clear the buffer, send, and read the status and the last
  frame check. The design ID is "HDLC".

Test hooks: top module `p_hdlc_tx_top`, ports named as in the board's master XDC, the test shell's `CLKS_PER_BIT`,
`TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `BIT_CYCLES` (clocks in one bit) as a top-level parameter.
