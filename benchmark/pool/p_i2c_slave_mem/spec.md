# I2C slave

I want the board to be an I2C peripheral that a microcontroller can talk to, on Pmod JB: JB1 is SCL and JB2 is SDA.

- Its 7-bit address is 0x2A. It answers to nothing else. It never holds the clock low. SDA is open drain: the
  FPGA only ever pulls it low or lets go. The master is not faster than 1 MHz.
- It has 16 one-byte registers. A write transfer sends the register number first, then data bytes that go to
  consecutive registers; a read transfer returns bytes from the current register number onwards, and the number moves on
  by one after each byte the slave sends. The number wraps from 15 back to 0.
- Register 0 reads as the part ID and cannot be written. Registers 1 to 7 are plain storage. Register 8 counts the data
  bytes written into registers 1 to 7 and stops at 255. Register 9 always reads as the XOR of registers 1 to 7.
  Registers 10 to 15 read as zero. A write to a register that cannot be written is acknowledged but ignored.
- A register number of 16 or more in a write is refused: the slave does not acknowledge that byte, nor the data bytes
  after it, and the current register number stays as it was.
- The register number is kept between transfers, so a read right after a write needs no pointer byte, and a repeated
  start works the usual way.
- The same registers can be read and written from the test shell (USB-UART, 115200 baud), together with how many
  transfers addressed this slave, how many register numbers were refused and the current register number. LED[7:0] show
  register 1. The design ID is "I2CS".

Test hooks: top module `p_i2c_slave_mem_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
