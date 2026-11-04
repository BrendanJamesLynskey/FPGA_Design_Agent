# CRC-8 engine

I want a small checksum engine for bytes sent from my PC.

- It computes an 8-bit CRC with the generator polynomial 0x1D (x^8 + x^4 + x^3 + x^2 + 1). It is bit-serial: it
  shifts one bit every few clocks, so a byte takes a while, and while it is working it is busy.
- A byte written while the engine is busy is not accepted: it is thrown away and counted. I want that count and the
  number of bytes the engine has taken.
- I can read the running CRC, and start again from the beginning.
- LED[7:0] show the CRC; LED[15] lights while the engine is busy.
- All of it goes through the test shell (USB-UART, 115200 baud). The design ID is "CR8E".

Test hooks: top module `p_crc8_engine_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `BIT_CLKS` (clocks the engine spends on each bit)
as a top-level parameter.
