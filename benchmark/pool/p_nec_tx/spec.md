# Infrared remote control transmitter

I want the board to act as a TV-remote-style transmitter, sending commands in the NEC style on Pmod JC pin 1, to an IR
LED.

- The IR light is switched on and off at a carrier frequency while a "mark" is being sent, and left off during a
  "space". I set the address and command bytes from the PC and then send.
- A frame is a long leader mark and a space, then 32 bits, then a final mark. Each bit is one short mark followed by a
  space: a short space for a 0 and a longer space for a 1. The 32 bits are the address, its complement, the command and
  its complement, each byte least significant bit first.
- If SW[0] is held up, the transmitter keeps sending short "repeat" codes after the frame, at a fixed repeat interval,
  as long as the switch stays up.
- LED[0] lights during a transmission, LED[15:8] show the command byte.
- Over the test shell (USB-UART, 115200 baud) I can set the address and command, send, and read the status and counts. The
  design ID is "NECT".

Test hooks: top module `p_nec_tx_top`, ports named as in the board's master XDC, the test shell's `CLKS_PER_BIT`,
`TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `UNIT_CYCLES` (the basic time unit in clocks) and `CARRIER_CYCLES`
(the carrier period in clocks, an even number) as top-level parameters.
