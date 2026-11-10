# Serial pattern spotter

I want the Nexys A7-100T to watch one serial input and tell me every time a particular pattern goes past.

- The input is Pmod JA pin 1 (JA1). On every clock edge the board takes in whatever bit is on that pin, so a bit
  lasts one clock.
- The pattern is 1, 0, 1, 1, with the oldest bit first. LED[0] lights for one clock each time the bits just taken
  in end in that pattern. The pin is not synchronous to the clock, so I expect it through two flip-flops first, and
  LED[0] to light two clocks after the edge that takes in the pattern's last bit. The other LEDs stay off.
- I want to know how many times it has been spotted, so keep a count, and let me clear it.
- CPU_RESETN resets everything.
- Over the test shell (USB-UART, 115200 baud) I can read the count and clear it, and read the level of the input.
  The design ID is "SQDT".

Test hooks: top module `v2_a_seq_detect_top`, ports named as in the board's master XDC, and the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters.
