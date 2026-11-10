# Priority encoder

I want the 16 slide switches of the Nexys A7-100T to act as 16 requests, and the board to say which request wins.

- When several switches are up, the highest-numbered one wins: SW[15] beats everything, SW[0] loses to everything.
- The winner is shown as a single lit LED: LED[n] for switch n. If no request is active, all LEDs are off.
- I also want a mask I can set over the shell: a request whose mask bit is set is ignored, as if its switch were
  down.
- CPU_RESETN resets everything, which leaves nothing masked.
- Over the test shell (USB-UART, 115200 baud) I can read the switches, read and set the mask, and read the number
  of the winning request together with a flag that says a request is active. The design ID is "PENC".

Test hooks: top module `v2_a_prio_enc_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
