# t2_sevenseg_marquee: reviewer notes

- **Twin:** the textbook's hex 7-segment decoder (and the button-counter display projects).
- **Trap:** `test_raw_segment_bytes` writes bytes that are not hex glyphs (0x49 = a, d, g; 0x80 = DP alone, ...);
  the trap variant passes the low nibble through a hex decoder and fails.
- **Left out of spec.md on purpose:** which digit shows MSG[POS] (leftmost), the modulo rule for the window, DIM's
  exact on-time ((DIM + 1)/8 of the slot, from the start of the slot), the scroll-counter restart rule, LENGTH/POS
  write rules, reset values (LENGTH 8, DIM 7).
- **Review:** the dim check measures every lit run exactly ((DIM + 1) * 2^(REFRESH_BITS-3) clocks); with
  REFRESH_BITS = 4 in the bench a run is 2..16 clocks. The scroll period check allows +/- 8 slots of observation
  granularity; the POS read checks land half a step away from a step.
- Reference RTL timing fix (after the lead's Vivado run, WNS -20.9 ns on pos -> seg_n): the per-digit message index
  is now an 8-stage register pipeline (dix[7] = POS, dix[k-1] = dix[k] + 1 wrapped at LENGTH) instead of a
  combinational modulo; a POS/LENGTH change settles within 8 clocks, invisible at the spec's slot level.
