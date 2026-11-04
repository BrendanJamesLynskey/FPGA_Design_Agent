# SPI slave

I want the board to be a peripheral that another microcontroller can talk to over SPI on Pmod JB, with a small bank of
registers behind it.

- Wiring: JB1 is chip select (active low), JB2 the clock, JB3 data from the master and JB4 data back to the master.
  SPI mode 0: data is sampled on the rising clock edge and changes on the falling edge, most significant bit first. The
  clock is never faster than 10 MHz.
- Every transfer starts with a command byte: the top bit says read (1) or write (0), the low seven bits are a register
  address. The bytes that follow, as long as chip select stays low, are the data, and the address moves on by one
  after each data byte.
- There are 16 registers of 8 bits. Register 0 reads back as the part ID and cannot be written. Registers 1 to 7 are
  plain storage. Register 8 always reads as the XOR of registers 1 to 7. Registers 9 to 15 read as zero. An address of
  16 or more reads as 0xFF and cannot be written.
- If chip select is released in the middle of a byte, that last partial byte does nothing and the transfer is counted
  as bad.
- The same registers can also be read and written from the test shell (USB-UART, 115200 baud), together with a count of
  transfers, a count of bad transfers and the last command byte. LED[7:0] show the last command byte. The design
  ID is "SPIS".

Test hooks: top module `p_spi_slave_regs_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
