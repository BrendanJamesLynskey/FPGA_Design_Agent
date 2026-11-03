# Period meter

I want to measure how long it is between pulses on SW[0], in clocks, as a piece of lab gear.

- Each time SW[0] goes from down to up that is an edge. The time from one edge to the next is a period. I want the
  latest period, the shortest and the longest since the last clear, and how many periods have been measured.
- If the edges stop coming for too long the meter should say so with a flag, rather than showing a stale reading as if it
  were current. When the edges come back, the first one only restarts the measurement; the period across the gap is
  not a valid reading and is not recorded.
- The 16 LEDs show the latest period as a binary number, held at 65535 if it is longer.
- Over the test shell (USB-UART, 115200 baud) I can read all of that and clear the shortest, longest and count. The
  design ID is "PRDM".

Test hooks: top module `p_period_meter_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `TIMEOUT_PERIOD` (clocks without an edge after which
the meter calls the input stalled) as a top-level parameter.
