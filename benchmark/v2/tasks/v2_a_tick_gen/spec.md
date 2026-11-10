# Programmable tick generator

I want a tick generator on the Nexys A7-100T: a pulse that other logic could use as an enable, coming round every
N clocks, with N set over the shell.

- LED[0] shows the tick. LED[1] changes state each time a tick happens, so it shows the ticks at half rate; it
  changes on the same clock edge on which LED[0] goes high, not a clock earlier or later. The other LEDs stay off.
- N is a number I write; zero means no ticks at all. The ticks should be exactly N clocks apart, not roughly.
- Keep a count of the ticks, and let me clear it.
- CPU_RESETN resets everything: N goes back to 8 and the ticks run from then on, so there is something to see
  before I write anything, and the tick count goes to zero.
- Over the test shell (USB-UART, 115200 baud) I can read and set N, and read and clear the tick count. The design
  ID is "TICK".

Test hooks: top module `v2_a_tick_gen_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
