# Oracle ambiguity list for v2_o_rms_meter (what spec.md leaves out on purpose)

1. Both roundings: the mean square is floored, the square root is the floor (integer root).
2. That the squares are summed at full width and divided once at the end.
3. The publishing instant: with the block, not per sample; the reading and the count move together.
4. What the control does to the count and the reading (nothing) and which bit it uses.
5. Register offsets, reset values, what SAMPLE reads back, what FILL counts (0 .. N-1).
6. The block length used on the board (256) against the bench (8): `RMS_LOG2` is a test hook.

Not testable through the shell: the 16-bit wrap of WINDOWS (65 536 blocks).
