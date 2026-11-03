# One-wire style ID reader

I have a little device that answers on a single wire, which is on Pmod JA pin 1. I want to read its 16-bit ID.

- The wire is open drain: the FPGA only ever pulls it low, never drives it high, and the line's pull-up does the rest.
- To talk to the device the FPGA first pulls the line low for a reset time and lets go. A device that is there answers by
  pulling the line low for a while shortly afterwards; I want to know whether it did.
- If it is there, the FPGA sends it the command 0x33, one bit per time slot with the least significant bit first. A
  slot starts with the FPGA pulling the line low: briefly for a 1, for most of the slot for a 0.
- Then it reads back 24 bits, again one per slot, least significant bit first: the 16-bit ID and an 8-bit CRC of the two
  ID bytes (low byte first). To read a bit the FPGA pulls low briefly, lets go and looks at the line a little later: if
  the device is holding it low the bit is a 0.
- The CRC is the Dallas/Maxim 8-bit one. I want to know whether it matched.
- LED[15:0] show the ID last read. Over the test shell (USB-UART, 115200 baud) I can start a read, and read the ID, the received
  CRC, the status and a count of failed reads (no device, or a CRC mismatch). The design ID is "1WID".

Test hooks: top module `p_onewire_id_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `RST_LOW`, `PRES_WAIT`, `PRES_LOW`, `PRES_SAMPLE`,
`RST_TOTAL`, `SLOT`, `W1_LOW`, `W0_LOW`, `RD_LOW`, `RD_SAMPLE` and `RD0_HOLD` as top-level parameters (all in clocks:
the reset low time, the device's answer delay and length, when the FPGA looks for the answer and how long the reset phase
lasts, the slot length, the low times of a written 1 and 0, the FPGA's read pulse, when it samples a read bit and how
long the device holds a 0).
