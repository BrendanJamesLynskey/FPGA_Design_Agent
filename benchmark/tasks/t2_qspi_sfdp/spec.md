# Read the configuration flash's ID and SFDP header

I want to identify the Nexys A7-100T's configuration flash from the FPGA after it has booted: read its JEDEC ID
and the start of its SFDP table (the standard self-description), and show them over the test shell.

- Single-bit SPI only, mode 0. The flash clock goes out through the configuration clock pin, so it has to go
  through the STARTUPE2 primitive. Keep the write-protect line low and the hold line high.
- On a start command: read the 3-byte JEDEC ID, then read 16 bytes of SFDP data from address 0 (the SFDP header and
  the first parameter header), with the dummy clocks the SFDP read needs.
- Registers: the ID, the 16 SFDP bytes as four words, and status (busy, done, and whether the first four SFDP bytes
  are the "SFDP" signature).
- This flash holds the board's bitstream: the design must never send anything but those two read commands.
- The SPI clock half period is a parameter in clocks (5 MHz on the board is plenty).
- Design ID "SFDP".

Test hooks: top module `t2_qspi_sfdp_top`, ports named as in the board's master XDC (`QSPI_CSN`, `QSPI_DQ0`..
`QSPI_DQ3`, the USB-UART pins, `CLK100MHZ`, `CPU_RESETN`), the test shell's `CLKS_PER_BIT`, `TIMEOUT_CYCLES` and
`BUILD_STAMP` parameters, plus `HALF` (SPI clock half period in clocks) as top-level parameters.
