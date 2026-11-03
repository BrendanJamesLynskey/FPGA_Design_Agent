# Electronic dice from an LFSR

I want a dice on the Nexys A7-100T, driven by a 16-bit Galois LFSR.

- Each press of BTNC (it bounces, so debounce it) steps the LFSR once and rolls a number from 1 to 6, taken from
  the LFSR state as (state mod 6) + 1. The roll shows on the rightmost 7-segment digit; the other digits stay dark.
- The feedback taps are a register, starting at 0xB400. I can also load the state (a seed) and make the LFSR step
  any number of times without rolling. The state must never get stuck at zero.
- Keep a history of the last four rolls and a count of rolls.
- CPU_RESETN resets everything, the state to 0xACE1.
- Over the test shell (USB-UART, 115200 baud) I can read the state, the last roll, the history and the roll count,
  set the seed and the taps, and ask for a number of steps. The design ID is "DICE".

Test hooks: top module `t1_lfsr_dice_top`, ports named as in the board's master XDC, the test shell's
`CLKS_PER_BIT`, `TIMEOUT_CYCLES` and `BUILD_STAMP` parameters, plus `DEBOUNCE_CYCLES` (debounce time in clocks) and
`REFRESH_BITS` (each display digit is lit for 2^REFRESH_BITS clocks) as top-level parameters.
