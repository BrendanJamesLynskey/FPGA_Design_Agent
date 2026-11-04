# t2_pdm_vu: reviewer notes

- **Twin:** the textbook's PDM microphone capture (M_LRSEL low, data at the rising edge, record/playback).
- **Trap:** `test_lrsel_high_falling_edge`: the bench's microphone model drives valid data only in the half that
  M_LRSEL selects (high half for M_LRSEL = 1) and random garbage in the other half; the test also checks M_LRSEL is
  never low. The trap variant (M_LRSEL low, rising-edge sampling) fails on the pin check.
- **Left out of spec.md on purpose:** register map; LEVEL formula details (|ONES - WINDOW/2|); the exact peak rule
  (hold reload, decay floor at 0), its units (blocks), reset values (HOLD 8, DECAY 1); LED thresholds
  ((i + 1) * WINDOW/32); the sample point in clocks; M_CLK phase after reset.
- **Review:** registers change every block (2048 clocks in the bench) while a shell read takes ~1200 clocks, so each
  check reads BLOCKS, the register, BLOCKS and accepts the model's value at any block count in between. The model
  computes every block from the bit stream the microphone model plays (`bit(j)` for M_CLK cycle j).
- The tests do not pin which microphone cycle starts block 0 (the bench's bit patterns are periodic within a block,
  or padded by a few samples around block boundaries), so a design whose blocks are offset by a sample or two from
  the spec's "first sample after reset" still passes in the padded tests; WINDOW, the sample edge and the counts are
  exact. (v1.2: the first part of `test_peak_hold_and_decay` gives the loud pattern no padding, so there an offset of
  a sample changes the PEAK values; deferred to v2.)
