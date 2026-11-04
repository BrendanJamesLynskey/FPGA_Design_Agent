# t2_vga_sprite: reviewer notes

- **Twin:** none (the textbook has a VGA text console, not a sprite). Trap: none.
- **Left out of spec.md on purpose:** register map; row bit order (bit 15 = leftmost); clipping (no wrap; X up to
  1023 hides it); the exact bounce rule (limits 624 / 464 = screen - 16, turn-and-step-back at the limit, X >= 624
  also catches positions written beyond it, update at the frame wrap); EN reset 1; FRAME; that changes act at once.
- **Review:** pixels are sampled on the third clock of each 4-clock pixel (one clock of colour/sync skew either way
  passes). Icarus runs this design at about 11 k clocks/s, so only `test_bounce_and_vertical_timing` crosses a frame
  wrap (one, 1.68 M clocks): it starts at X = 624, Y = 0 moving up so both turns happen at that wrap, and checks VS
  timing and the blank lines on the way. Plain +-1 steps away from the edges and BOUNCE = 0 holding still are in the
  spec but not simulated (they would need more frames); a reviewer may want a longer optional run.
- **v1.1 (2026-11-03):** the self-check's bounce rule brackets the frame count (the v1 window was a measurement error on
  the board); three tests added for the recorded survivors (X far off the right, CTRL.EN = 0 and blanking lines over a
  non-zero background, each looked at where the fault can show; a turn at X = 0 and at Y = 464). The reference passes
  9/9 on Icarus; the mutant check of the four survivors is the planner's.
- 2026-11-04 (planner): the four ran as mutants on Icarus and were all killed; they moved into `mutants`
  (`known_survivors: []`). Full re-check: reference 9/9, mutants 9/9 killed, 23:45-01:24 (single job, HDD root).
