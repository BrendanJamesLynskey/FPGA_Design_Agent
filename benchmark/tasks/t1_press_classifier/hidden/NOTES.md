# t1_press_classifier: reviewer notes

- **Twin:** the textbook button-press counter (Bruno project 3: debounced BTNC, every press counted on the display).
- **Trap:** `test_long_press_not_short`. The trap variant classifies every press as SHORT (the book's behaviour,
  counting all presses alike); long presses must raise LONG_COUNT and leave SHORT_COUNT alone.
- **Left out of spec.md on purpose:** how "held for" is measured (H = clocks the debounced level is high; both edges
  share the debounce delay, so H equals a clean press's width); whether the threshold is inclusive (yes); the unit
  and rounding of the length (floor of H / TICK_CYCLES, saturating at 0xFFFF); the register map and offsets; that
  count clears do not touch the LED toggles; LED[7:2] off; what STATUS holds.
- **Review:** `test_threshold_boundary` tests H = LONG_CYCLES - 1, LONG_CYCLES and + 1 exactly, so an agent that is
  one clock off in its high-time count fails it; spec.yaml defines H exactly, so the oracle can answer.
  `test_length_saturates` holds the button for about 200k clocks (TICK_CYCLES = 3 in the bench).
