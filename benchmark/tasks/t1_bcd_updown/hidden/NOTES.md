# t1_bcd_updown: notes for the reviewer

- **Twin:** the textbook's button-press counter with a decimal 7-segment display (assessment table 1b, project 3).
- **Trap:** `test_leading_zero_blanking`: this spec blanks leading zeros (zero shows a single 0); the textbook
  display shows all digits. The trap variant (mutants.yaml `trap`) lights every digit and fails it.
- **Left out of spec.md on purpose:** what happens when up and down land on the same clock (cancel); whether a
  write of 10000 or more is clamped or ignored (ignored); whether WRAPS counts both directions (yes) and how it is
  cleared (any write); the debounce rule and time; glyph shapes for 6, 7, 9.
- **Look at:** the wrap counter's width (8 bits) and that STEP is read from synchronised but not debounced switches.
