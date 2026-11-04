# t1_lfsr_dice: reviewer notes

- **Twin:** none (LFSRs appear in textbooks, but no Packt/Digilent project is a seeded dice with these registers).
  No trap.
- **Left out of spec.md on purpose:** Galois direction (right shift, taps XORed when the shifted-out bit is 1);
  what "never stuck at zero" means exactly (a step or SEED write that gives 0 gives 0x0001); whether the roll uses
  the state before or after the step (after); the history nibble order (newest in [3:0]); what happens to presses
  during a burst (lost); the register map; the display before the first roll (dark).
- **What is checked:** the seeded sequence register by register; the zero rule with taps chosen to reach 0
  (0x0400 / 0x0801); the maximal period with the reset taps (two 65535-step bursts, ~132k clocks); every glyph via
  seeds chosen with the model.
- **Review:** the bench does not test a STEP write during a burst (the "replaces the steps left" rule is off by one
  depending on how it is read).
- **v1.2 (2026-11-04):** `scan_display` now treats a digit with every segment and DP off as dark whether or not its
  anode is low; the burst rate and the lost press during a burst are listed under `assumptions`. Mutant
  `dark_digit_shows_zero` changed: its v1 form (digit 0 lit with a blank glyph) is dark, so equivalent to the reference;
  it now shows a 0 glyph. A STEP write during a burst is still untested (deferred to v2).
