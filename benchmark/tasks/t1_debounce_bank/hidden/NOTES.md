# t1_debounce_bank: reviewer notes

- **Twin:** the textbook debouncer that samples the (synchronised) input once per slow tick (Bruno project 3's
  safe-input chapter; common in Digilent demos).
- **Trap:** `test_glitch_on_slow_tick`. The trap variant turns the reference debouncer into a free-running tick
  sampler (the "restart on equal" branch removed): 3-clock glitches swept across every phase of a DEBOUNCE_CYCLES
  period, then DEBOUNCE_CYCLES - 1 and DEBOUNCE_CYCLES / 2 glitches, must change no level, count or flag.
- **Left out of spec.md on purpose:** the counter width (8 bits, wrapping) and packing (four per register); how
  counts are cleared (any write clears the register's four); the default edge selection (rising only); W1C; the
  register map; that a switch up at reset gives an edge.
- **Review:** `test_independent_timing` also checks the absolute settle latency (DEBOUNCE_CYCLES + 1..5 clocks from
  the pin change to the LED); the spec gives 2 (sync) + DEBOUNCE_CYCLES clocks for the level, plus the registered
  LED.
- **v1.2 (2026-11-04):** the absolute settle latency is accepted from n + 1 to n + 8 clocks (v1: n + 5), so a three- or
  four-flop synchroniser passes; the relative `n // 2` check still proves the switches are independent.
