# RC receiver channel reader

I want to read one channel of a radio-control receiver. It sends a positive pulse on Pmod JA pin 1 every 20 ms or so;
the pulse is about 1 ms wide at one end of the stick's travel and about 2 ms at the other.

- The design measures each pulse in clocks and turns the width into a position from 0 to 255, in proportion, with 0 at
  the narrow end and 255 at the wide end; anything outside the two end widths gives 0 or 255.
- A pulse that is much too narrow or much too wide cannot be a real one: it is counted as bad and ignored.
- If good pulses stop arriving for long enough (the radio is off or the wire is out) the design goes into failsafe and
  the position goes to the middle, 128, until a good pulse comes back.
- LED[7:0] show the position, LED[14] whether the last pulse was good, LED[15] the failsafe.
- Over the test shell (USB-UART, 115200 baud) I can read the width, the position, the status and the counts of good
  and bad pulses, and clear the counts. The design ID is "SRVR".

Test hooks: top module `p_servo_rx_top`, ports named as in the board's master XDC, the test shell's `CLKS_PER_BIT`,
`TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `MIN_W` and `MAX_W` (the pulse widths in clocks at positions 0 and
255), `VALID_MIN` and `VALID_MAX` (the narrowest and widest pulse accepted) and `FAILSAFE_CYCLES` (clocks without a good
pulse before failsafe) as top-level parameters.
