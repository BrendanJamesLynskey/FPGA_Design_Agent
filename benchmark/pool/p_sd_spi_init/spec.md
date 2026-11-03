# SD card start-up in SPI mode

I want the board to wake up an SD card in SPI mode and find out what kind of card it is. Reading blocks comes later.

- The card slot wires the card for SPI: SD_SCK is the clock, SD_CMD is data to the card, SD_DAT0 is data from the card
  and SD_DAT3 is chip select (active low). SD_RESET switches the card's power: low means powered, and the design
  holds it high while it is in reset.
- After a power-up wait, the card needs at least 74 clock pulses with chip select high and the data line high, before
  it listens. Then comes the usual start-up conversation. Each command is six bytes: a command byte, a four-byte argument
  and a check byte. The card answers with a response byte (R1) some bytes later, which the design finds by sending
  idle bytes (0xFF) and looking for the first byte whose top bit is 0.
- Go idle (command 0, expecting R1 = 0x01). Ask about the interface condition (command 8 with argument 0x000001AA):
  a version 2 card repeats it back, an older card says the command is illegal. Then keep asking the card to start up
  (command 55 followed by command 41, which for a version 2 card asks for high-capacity support) until it says it is
  ready, giving up after a fixed number of tries. A version 2 card is finally asked for its operating conditions
  (command 58), and bit 30 of the answer tells a high-capacity card from a standard one.
- LED[3:0] show how far it has got, LED[5:4] the kind of card and LED[8] lights when the card is ready, LED[9] when
  it failed.
- Over the test shell (USB-UART, 115200 baud) I can read the state, the card type, the operating conditions word, the
  number of start-up tries and a code for what went wrong. The design ID is "SDIN".

Test hooks: top module `p_sd_spi_init_top`, ports named as in the board's master XDC, the test shell's `CLKS_PER_BIT`,
`TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `PWR_DELAY` (clocks of waiting after power is switched on),
`INIT_HALF` (clocks in half a clock period of SD_SCK), `MAX_TRIES` (the most start-up tries) and `RETRY_GAP` (clocks to
wait between tries) as top-level parameters.
