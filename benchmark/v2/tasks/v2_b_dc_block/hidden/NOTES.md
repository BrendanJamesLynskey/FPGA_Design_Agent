# Notes for v2_b_dc_block

What spec.md does not say:
- the equation W = x - xp + yp - (yp >> 7), the arithmetic (floor) shift and that the feedback uses the limited output;
- that a positive output below 128 never decays (a consequence of the floor shift, stated as intended);
- queue depth 4, full-queue rule (keep the newest), the SAT and LOST bits;
- the register layout.

Trap: a symmetric (toward zero) pole term, which makes small positive offsets fade.
