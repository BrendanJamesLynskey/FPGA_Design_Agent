# On-demand temperature readings from the ADT7420

I want to take temperature readings from the board's ADT7420 sensor only when I ask, to save power, using its
one-shot mode instead of letting it convert all the time.

- The sensor sits on I2C at address 0x4B (TMP_SCL and TMP_SDA). One reading is: tell the sensor to do a single
  conversion by writing its configuration register (register 0x03) with the operation mode set to one-shot, wait long
  enough for the conversion to finish, then read the temperature register (0x00, two bytes).
- I choose the resolution: 13-bit or 16-bit. The sensor's resolution bit is bit 7 of the same configuration register.
- From the two bytes I want the temperature in sixteenths of a degree Celsius as a signed number. The last three bits
  of a 13-bit reading are not temperature.
- I want the lowest and highest reading since I last cleared, and how many readings there have been.
- If the sensor does not answer, the reading is abandoned and counted as an error; the bus must be left free.
- LED[15:0] show the latest temperature in sixteenths of a degree as a two's-complement number.
- Over the test shell (USB-UART, 115200 baud) I start a reading, choose the resolution, and read everything back. The
  design ID is "T7OS".

Test hooks: top module `p_adt7420_oneshot_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `QUARTER` (clocks in a quarter of an SCL period) and
`CONV_WAIT` (clocks to wait between the configuration write and the temperature read) as top-level parameters.
