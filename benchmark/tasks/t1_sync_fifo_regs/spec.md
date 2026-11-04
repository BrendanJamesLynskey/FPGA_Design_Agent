# Byte FIFO behind the test shell

I want a small FIFO on the Nexys A7-100T that I can exercise entirely from the test shell: 16 entries of 8 bits.

- Writing a byte to a push register adds it at the tail. Reading a pop register returns the byte at the head and
  removes it. I also want to look at the head byte without removing it, and to read how many bytes are stored.
- Flags: empty, full, and an almost-full flag whose threshold I can set over the shell.
- Pushing into a full FIFO loses the byte; popping an empty FIFO returns 0. Both mistakes must be remembered in
  sticky error flags until I clear them, each on its own.
- The LEDs show the fill level as a bar graph growing from LED[0].
- CPU_RESETN empties the FIFO and clears every flag.
- The shell runs at 115200 baud on the USB-UART. The design ID is "FIFO".

Test hooks: top module `t1_sync_fifo_regs_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters as top-level parameters. There are no other time
constants.
