# Decimal up/down counter with selectable step

I want a four-digit decimal counter on the Nexys A7-100T.

- BTNU counts up and BTND counts down. Each press moves the count by the step chosen on the two right-hand
  switches: SW[1:0] = 00 gives 1, 01 gives 2, 10 gives 5 and 11 gives 10. The buttons bounce, so one press must
  move it exactly once.
- The count runs from 0000 to 9999 and wraps round at both ends (going up past 9999 carries on from the bottom,
  going down past 0 carries on from the top). I'd like to know how many times it has wrapped; a single byte is
  plenty, so after 255 that count can go round to zero.
- The right-hand four digits of the 7-segment display show the count in decimal, without leading zeros: 7 shows
  as a single 7, and zero shows as a single 0. The other digits stay dark.
- LED[13:0] show the count in binary.
- CPU_RESETN resets everything to zero.
- Over the test shell (USB-UART, 115200 baud) I can read the count (binary and as BCD digits), set it, read the
  wrap count, and read the step the switches select. The design ID is "BCDU".

Test hooks: top module `t1_bcd_updown_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `DEBOUNCE_CYCLES` (debounce time in clocks) and
`REFRESH_BITS` (each display digit is lit for 2^REFRESH_BITS clocks) as top-level parameters.
