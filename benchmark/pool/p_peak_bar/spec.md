# Bar graph with a peak marker

I want the 16 LEDs to work as a level meter driven by the switches.

- SW[7:0] are an 8-bit level. The LEDs show it as a bar from LED[0] upwards: the bigger the level, the more LEDs lit,
  all 16 for a full-scale level and none for zero. A level of 1 should already light one LED.
- A single extra LED marks the highest bar length seen recently. It jumps up with the bar instantly, but when the
  level falls it creeps down one LED at a time at a slow, fixed rate until it meets the bar.
- SW[15] up wipes the marker down to the bar at once.
- Over the test shell (USB-UART, 115200 baud) I can read the bar length, the marker position and the highest raw
  level seen. The design ID is "PKBR".

Test hooks: top module `p_peak_bar_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `DECAY_CYCLES` (clocks per marker step) as a
top-level parameter.
