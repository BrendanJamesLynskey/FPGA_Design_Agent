# Notes for v2_b_comp_fir

What spec.md does not say:
- the coefficients [2, -6, 16, -48, 584, -48, 16, -6, 2] (sum 512) and the shift 9;
- the rounding (add 256, arithmetic shift: ties up) and the saturation limits;
- that the history keeps the written samples, not the saturated results;
- queue depth 8, and that a full queue keeps the newest entries (the oldest is discarded);
- register layout (CTRL, SAMPLE, STATUS, RESULT, NEXT) and the SAT/LOST bits.

Trap: a bare arithmetic shift (no rounding offset). The tie samples are +32 and -32 (ACC = +-18688), which separate half-up
rounding from truncation and from half-away rounding.

The DC gain is exactly one, but the step response overshoots to 1.07, so a full-scale DC input saturates; the tests use 30000.
