# Byte-command I2C master on the temperature-sensor bus

I want to talk to the Nexys A7-100T's on-board I2C bus (the ADT7420 temperature sensor's TMP_SCL / TMP_SDA) from a
script, one bus operation at a time, so I can try any register sequence without rebuilding the FPGA.

- Four commands I can issue over the test shell: START, WRITE a byte, READ a byte, STOP. A START while I already
  have the bus must come out as a repeated START. A WRITE records whether the slave acknowledged. A READ is told
  whether to answer ACK (more to come) or NACK (last byte).
- Status shows busy and whether the last written byte was NACKed; the last byte read is in a register.
- The lines are open drain with the board's pull-ups: never drive them high. Slaves may stretch the clock and the
  master must wait for them.
- SCL speed: set by a parameter giving a quarter of the SCL period in clocks (equal high and low halves); on the
  board I'd like 100 kHz.
- Design ID "I2CM".

Test hooks: top module `t2_i2c_cmd_master_top`, ports named as in the board's master XDC (`TMP_SCL`, `TMP_SDA`,
the USB-UART pins, `CLK100MHZ`, `CPU_RESETN`), the test shell's `CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP`
parameters, plus `QUARTER` (a quarter of the SCL period, in clocks) as top-level parameters.
