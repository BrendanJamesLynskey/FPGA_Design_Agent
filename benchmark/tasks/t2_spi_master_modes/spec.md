# General-purpose SPI master on Pmod JB

I want an SPI master on Pmod JB of the Nexys A7-100T that I can point at whatever SPI part I plug in later, so it
must not assume one device.

- Pins: JB1 is chip select (active low), JB2 MOSI, JB3 MISO, JB4 SCLK.
- All four SPI modes (clock polarity and phase both selectable), MSB-first by default with an LSB-first option,
  and 8-bit or 16-bit frames.
- SCLK speed from a divisor register that gives the SCLK half period in 100 MHz clocks; 2 is the smallest that
  makes sense, so anything smaller is not accepted. After reset I'd like 1 MHz.
- Normally chip select goes low for one frame and back high after it, but I need a "hold" setting that keeps it low
  across several frames (for parts that want a command and then data in one select), and releases it when I clear
  the setting.
- Writing the transmit register starts a frame. The received frame is readable afterwards. Status: busy, and a
  done flag I clear by writing 1 to it.
- With nothing plugged in I still want to test it on the board, so add an internal loopback (MISO fed from our
  own MOSI).
- Everything through the test shell; design ID "SPIM".

Test hooks: top module `t2_spi_master_modes_top`, ports named as in the board's master XDC (`JB1`, `JB2`, `JB3`,
`JB4`, the USB-UART pins, `CLK100MHZ`, `CPU_RESETN`), the test shell's `CLKS_PER_BIT`, `TIMEOUT_CYCLES` and
`BUILD_STAMP` parameters as top-level parameters. The SCLK rate comes only from the divisor register.
