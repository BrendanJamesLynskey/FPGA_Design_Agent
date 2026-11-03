# Retriggerable pulse stretcher

I want to turn a quick flick of a switch into an LED pulse I can actually see.

- Flipping SW[0] from down to up starts a pulse: LED[0] lights and stays lit for a fixed time. If SW[0] is flipped up
  again while the LED is still lit, the pulse is stretched, not doubled: the LED then stays lit for the full time
  counted from that latest flip.
- LED[1] tells me that the current pulse has been retriggered at least once; it goes dark when the pulse ends.
- I would like to read back how many flips there have been, how many of them landed on a lit LED, and the longest
  time the LED has stayed lit in one go.
- CPU_RESETN puts everything back to the start.
- Over the test shell (USB-UART, 115200 baud) I can read those figures and clear them. The design ID is "PSTR".

Test hooks: top module `p_pulse_stretch_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `HOLD_CYCLES` (the lit time in clocks) as a
top-level parameter.
