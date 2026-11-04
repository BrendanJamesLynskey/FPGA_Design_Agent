# t1_pattern_sequencer: reviewer notes

- **Twin:** none. No trap.
- **Left out of spec.md on purpose:** the register map (entries at 0x10..0x1F, pattern and duration packed); DUR = 0
  meaning 256 ticks; what the LEDs show when stopped (dark) versus after a one-shot (last pattern held); that the
  duration is latched at entry start while the pattern is read live; what a RUN = 1 write does while running (no
  restart); when a LENGTH change takes effect (next entry end); LOOPS counting a finished one-shot; LENGTH's legal
  range; that entries survive reset.
- **How it is checked:** a watcher logs LED changes; each playback is compared as (pattern, clocks shown) pairs with
  the model's schedule, so all durations are exact and no absolute start time is needed. Patterns in a test are
  distinct so every entry change is visible.
- **Review:** pause timing is exact: the paused time is the clock difference between the two pause presses' pin rises.
