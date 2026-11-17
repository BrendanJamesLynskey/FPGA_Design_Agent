# Oracle ambiguity list for v2_o_peak_meter (what spec.md leaves out on purpose)

1. The size of the fall: a thirty-second of the reading per sample, with a floor of one (spec.md says "a fraction of itself").
2. The default hold time (32 samples) and that HOLD is only read when the timer is reloaded.
3. That an equal magnitude re-arms the hold (">=" not ">").
4. The magnitude of the most negative sample (0x800000).
5. That the clip count is per sample; that it is only the two end values, not "near" them.
6. That the clears are independent, on bits 0 and 1 of CTRL, and which register holds them.
7. Register offsets and reset values; what SAMPLE reads back.

Not testable through the shell: the saturation of CLIPS at 0xFFFF (65 535 samples at about 1 200 clocks each). The
spec states it; the mutant list therefore has no saturation mutant.
