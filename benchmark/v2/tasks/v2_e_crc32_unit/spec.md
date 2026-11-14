# Frame check unit

I want a small checking block for network packets, built for the Nexys A7-100T. It computes the 32-bit cyclic redundancy
check that Ethernet uses (the same one `zlib.crc32` computes in Python) over the bytes I give it, one byte at a time, and it
tells me when a packet that ends in its own check value is intact.

- Starting a new packet is a "clear": the running check goes back to its start state and the byte count to zero.
- Each byte I write to the data register is the next byte of the packet. The check is the standard one: reflected, the
  polynomial 0xEDB88320, start value 0xFFFFFFFF, final inversion. Reading the check register at any time gives the check of
  the bytes written since the last clear (the check of no bytes is zero).
- A sender appends the check to its packet with the low byte first. So when I write a packet and then its four check bytes in
  that order, the unit must report "intact" through a flag; the flag must be false for every other situation, including
  the moment before the last check byte arrives and a packet with one bit wrong.
- The unit also counts the bytes written since the last clear, as a 16-bit number that wraps.
- LED[15:0] shows the low 16 bits of the check register.
- CPU_RESETN resets everything to the state after a clear.
- Everything above is reachable through the test shell on the USB-UART at 115200 baud, and the design ID it reports is "FCU1".

For the bench: the top module is called `v2_e_crc32_unit_top`, its ports carry the names the board's master XDC uses, and it
takes the shell's three parameters `CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP`.
